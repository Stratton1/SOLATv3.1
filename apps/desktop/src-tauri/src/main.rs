// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs;
use std::io::{BufRead, BufReader};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command as StdCommand, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::Manager;

struct EngineProcess(Mutex<Option<Child>>);

/// Persistent log file path for engine boot output.
struct EngineLogPath(Mutex<PathBuf>);

const ENGINE_PORT: u16 = 8765;
const HEALTH_WAIT_SECS: u64 = 12;

// ---------------------------------------------------------------------------
// Port management
// ---------------------------------------------------------------------------

fn port_is_occupied() -> bool {
    TcpStream::connect_timeout(
        &format!("127.0.0.1:{}", ENGINE_PORT).parse().unwrap(),
        Duration::from_millis(500),
    )
    .is_ok()
}

fn kill_port_occupant() {
    println!("[SOLAT] Killing stale process on port {}...", ENGINE_PORT);
    let output = StdCommand::new("lsof")
        .args(["-ti", &format!(":{}", ENGINE_PORT)])
        .output();

    if let Ok(output) = output {
        let pids = String::from_utf8_lossy(&output.stdout);
        for pid_str in pids.split_whitespace() {
            if let Ok(pid) = pid_str.trim().parse::<i32>() {
                println!("[SOLAT] Killing PID {} on port {}", pid, ENGINE_PORT);
                let _ = StdCommand::new("kill")
                    .args(["-9", &pid.to_string()])
                    .output();
            }
        }
    }
    std::thread::sleep(Duration::from_millis(500));
}

fn ensure_port_free() {
    if port_is_occupied() {
        kill_port_occupant();
        if port_is_occupied() {
            eprintln!(
                "[SOLAT] WARNING: Port {} still occupied after kill attempt",
                ENGINE_PORT
            );
        } else {
            println!("[SOLAT] Port {} freed successfully", ENGINE_PORT);
        }
    }
}

// ---------------------------------------------------------------------------
// Engine directory + uv resolution
// ---------------------------------------------------------------------------

fn find_engine_dir() -> Option<PathBuf> {
    let candidates = [
        // From project root
        std::env::current_dir().ok().map(|p| p.join("engine")),
        // From src-tauri/
        std::env::current_dir()
            .ok()
            .map(|p| p.join("../../../engine")),
        // Absolute fallback via CARGO_MANIFEST_DIR
        Some(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../engine")),
    ];

    for candidate in candidates.into_iter().flatten() {
        if let Ok(resolved) = candidate.canonicalize() {
            if resolved.join("solat_engine").is_dir() {
                return Some(resolved);
            }
        }
    }
    None
}

/// Resolve the absolute path to `uv` using a login shell (picks up ~/.zshrc PATH).
/// Falls back to common known locations if shell resolution fails.
fn resolve_uv_path() -> Option<PathBuf> {
    // Try login shell first (works even when Tauri is launched from Finder)
    if let Ok(output) = StdCommand::new("/bin/zsh")
        .args(["-lc", "command -v uv"])
        .output()
    {
        let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !path.is_empty() {
            let p = PathBuf::from(&path);
            if p.exists() {
                println!("[SOLAT] Resolved uv via login shell: {}", path);
                return Some(p);
            }
        }
    }

    // Fallback: check common install locations
    let fallbacks = [
        dirs::home_dir().map(|h| h.join(".local/bin/uv")),
        dirs::home_dir().map(|h| h.join(".cargo/bin/uv")),
        Some(PathBuf::from("/usr/local/bin/uv")),
        Some(PathBuf::from("/opt/homebrew/bin/uv")),
    ];

    for candidate in fallbacks.into_iter().flatten() {
        if candidate.exists() {
            println!("[SOLAT] Found uv at fallback: {}", candidate.display());
            return Some(candidate);
        }
    }

    None
}

// ---------------------------------------------------------------------------
// Log file management
// ---------------------------------------------------------------------------

fn engine_log_path(engine_dir: &PathBuf) -> PathBuf {
    let log_dir = engine_dir.join("data").join("logs");
    let _ = fs::create_dir_all(&log_dir);
    log_dir.join("engine-boot.log")
}

fn read_log_tail(path: &PathBuf, lines: usize) -> String {
    match fs::read_to_string(path) {
        Ok(content) => {
            let all_lines: Vec<&str> = content.lines().collect();
            let start = if all_lines.len() > lines {
                all_lines.len() - lines
            } else {
                0
            };
            all_lines[start..].join("\n")
        }
        Err(_) => String::from("(no log file found)"),
    }
}

// ---------------------------------------------------------------------------
// Engine spawn
// ---------------------------------------------------------------------------

fn spawn_engine(log_path: &PathBuf) -> Result<Child, String> {
    let engine_dir = find_engine_dir().ok_or("Could not find engine directory")?;

    println!("[SOLAT] Starting engine from: {}", engine_dir.display());
    println!("[SOLAT] Log file: {}", log_path.display());

    // Open log file for stdout+stderr redirect (not piped — avoids buffer deadlock)
    let log_file = fs::File::create(log_path)
        .map_err(|e| format!("Failed to create log file: {}", e))?;
    let log_file_err = log_file
        .try_clone()
        .map_err(|e| format!("Failed to clone log file handle: {}", e))?;

    // Resolve uv path (GUI apps don't inherit terminal PATH)
    let uv_path = resolve_uv_path();

    let child = if let Some(uv) = &uv_path {
        println!("[SOLAT] Using uv at: {}", uv.display());
        StdCommand::new(uv)
            .args([
                "run",
                "python",
                "-m",
                "uvicorn",
                "solat_engine.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                &ENGINE_PORT.to_string(),
                "--log-level",
                "info",
            ])
            .current_dir(&engine_dir)
            .stdout(Stdio::from(log_file))
            .stderr(Stdio::from(log_file_err))
            .spawn()
            .map_err(|e| format!("Failed to spawn engine via uv: {}", e))?
    } else {
        // Fallback: try python3 directly (assumes venv is activated or system python works)
        eprintln!("[SOLAT] uv not found, falling back to python3 -m uvicorn");
        let venv_python = engine_dir.join(".venv/bin/python3");
        let python_cmd = if venv_python.exists() {
            venv_python.to_string_lossy().to_string()
        } else {
            "python3".to_string()
        };

        println!("[SOLAT] Using python at: {}", python_cmd);
        StdCommand::new(&python_cmd)
            .args([
                "-m",
                "uvicorn",
                "solat_engine.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                &ENGINE_PORT.to_string(),
                "--log-level",
                "info",
            ])
            .current_dir(&engine_dir)
            .stdout(Stdio::from(log_file))
            .stderr(Stdio::from(log_file_err))
            .spawn()
            .map_err(|e| format!("Failed to spawn engine via python3: {}", e))?
    };

    Ok(child)
}

/// Kill stale port occupant, spawn engine, wait for health.
fn force_start_engine(log_path: &PathBuf) -> Result<Child, String> {
    ensure_port_free();
    let mut child = spawn_engine(log_path)?;
    let pid = child.id();
    println!("[SOLAT] Engine spawned (pid {}), waiting for health...", pid);

    // Wait for engine to become healthy (or detect early exit)
    let start = Instant::now();
    let deadline = Duration::from_secs(HEALTH_WAIT_SECS);

    while start.elapsed() < deadline {
        // Check if child exited early
        match child.try_wait() {
            Ok(Some(status)) => {
                let tail = read_log_tail(log_path, 20);
                return Err(format!(
                    "Engine exited immediately with status: {}.\nLast log lines:\n{}",
                    status, tail
                ));
            }
            Ok(None) => {} // still running, good
            Err(e) => {
                return Err(format!("Failed to check engine status: {}", e));
            }
        }

        // Check if health endpoint responds
        if port_is_occupied() {
            // Port is open — try an actual HTTP health check
            if let Ok(output) = StdCommand::new("curl")
                .args([
                    "-sS",
                    "--max-time",
                    "2",
                    &format!("http://127.0.0.1:{}/health", ENGINE_PORT),
                ])
                .output()
            {
                let body = String::from_utf8_lossy(&output.stdout);
                if body.contains("healthy") {
                    println!(
                        "[SOLAT] Engine healthy after {:.1}s",
                        start.elapsed().as_secs_f64()
                    );
                    return Ok(child);
                }
            }
        }

        std::thread::sleep(Duration::from_millis(500));
    }

    // Timeout — engine is still running but not healthy
    let tail = read_log_tail(log_path, 20);
    eprintln!(
        "[SOLAT] WARNING: Engine pid {} not healthy after {}s. Log tail:\n{}",
        pid, HEALTH_WAIT_SECS, tail
    );
    // Return the child anyway — splash screen will keep polling
    Ok(child)
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

#[tauri::command]
async fn start_engine(
    proc_state: tauri::State<'_, EngineProcess>,
    log_state: tauri::State<'_, EngineLogPath>,
) -> Result<String, String> {
    // Kill existing managed child
    {
        let mut guard = proc_state.0.lock().map_err(|e| e.to_string())?;
        if let Some(ref mut child) = *guard {
            let _ = child.kill();
            let _ = child.wait();
            *guard = None;
        }
    }

    let log_path = log_state.0.lock().map_err(|e| e.to_string())?.clone();
    let child = force_start_engine(&log_path)?;
    let pid = child.id();

    {
        let mut guard = proc_state.0.lock().map_err(|e| e.to_string())?;
        *guard = Some(child);
    }

    Ok(format!("Engine started (pid {})", pid))
}

#[tauri::command]
async fn stop_engine(state: tauri::State<'_, EngineProcess>) -> Result<String, String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(ref mut child) = *guard {
        child
            .kill()
            .map_err(|e| format!("Failed to kill engine: {}", e))?;
        let _ = child.wait();
        *guard = None;
        Ok("Engine stopped".to_string())
    } else {
        Ok("No engine process to stop".to_string())
    }
}

#[derive(serde::Serialize)]
struct EngineStatus {
    running: bool,
    pid: Option<u32>,
    health_ok: bool,
    health_body: Option<String>,
    health_error: Option<String>,
    log_tail: String,
    log_path: String,
}

#[tauri::command]
async fn get_engine_status(
    proc_state: tauri::State<'_, EngineProcess>,
    log_state: tauri::State<'_, EngineLogPath>,
) -> Result<EngineStatus, String> {
    let log_path = log_state.0.lock().map_err(|e| e.to_string())?.clone();

    let (running, pid) = {
        let mut guard = proc_state.0.lock().map_err(|e| e.to_string())?;
        match &mut *guard {
            Some(child) => {
                // Check if still alive
                match child.try_wait() {
                    Ok(Some(_status)) => {
                        // Process has exited
                        let pid = child.id();
                        *guard = None;
                        (false, Some(pid))
                    }
                    Ok(None) => (true, Some(child.id())),
                    Err(_) => (false, None),
                }
            }
            None => (false, None),
        }
    };

    // Try health check
    let (health_ok, health_body, health_error) = match StdCommand::new("curl")
        .args([
            "-sS",
            "--max-time",
            "2",
            &format!("http://127.0.0.1:{}/health", ENGINE_PORT),
        ])
        .output()
    {
        Ok(output) => {
            let body = String::from_utf8_lossy(&output.stdout).to_string();
            if body.contains("healthy") {
                (true, Some(body), None)
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr).to_string();
                (false, Some(body), Some(stderr))
            }
        }
        Err(e) => (false, None, Some(e.to_string())),
    };

    let log_tail = read_log_tail(&log_path, 30);

    Ok(EngineStatus {
        running,
        pid,
        health_ok,
        health_body,
        health_error,
        log_tail,
        log_path: log_path.to_string_lossy().to_string(),
    })
}

#[tauri::command]
async fn get_engine_log(log_state: tauri::State<'_, EngineLogPath>) -> Result<String, String> {
    let log_path = log_state.0.lock().map_err(|e| e.to_string())?.clone();
    read_log_tail_full(&log_path).map_err(|e| e.to_string())
}

fn read_log_tail_full(path: &PathBuf) -> Result<String, std::io::Error> {
    let file = fs::File::open(path)?;
    let reader = BufReader::new(file);
    let lines: Vec<String> = reader.lines().collect::<Result<_, _>>()?;
    // Return last 100 lines
    let start = if lines.len() > 100 {
        lines.len() - 100
    } else {
        0
    };
    Ok(lines[start..].join("\n"))
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

fn main() {
    // Compute log path early
    let engine_dir = find_engine_dir().unwrap_or_else(|| PathBuf::from("."));
    let log_path = engine_log_path(&engine_dir);

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(EngineProcess(Mutex::new(None)))
        .manage(EngineLogPath(Mutex::new(log_path.clone())))
        .invoke_handler(tauri::generate_handler![
            start_engine,
            stop_engine,
            get_engine_status,
            get_engine_log
        ])
        .setup(move |app| {
            // Non-blocking: spawn engine and return immediately.
            // The splash screen handles health polling and shows progress.
            println!("[SOLAT] Spawning engine (non-blocking)...");
            ensure_port_free();
            match spawn_engine(&log_path) {
                Ok(child) => {
                    let pid = child.id();
                    println!("[SOLAT] Engine spawned (pid {})", pid);
                    let state = app.state::<EngineProcess>();
                    let mut guard = state.0.lock().unwrap();
                    *guard = Some(child);
                }
                Err(e) => {
                    eprintln!("[SOLAT] Failed to spawn engine: {}", e);
                    // Don't panic — splash screen will show error and retry button
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
