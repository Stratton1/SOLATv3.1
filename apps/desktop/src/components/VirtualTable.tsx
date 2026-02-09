/**
 * Virtual/paginated table component for performance.
 *
 * When data exceeds maxRows, shows pagination controls instead
 * of rendering all rows. Optimizes for large datasets.
 */

import { useState, useMemo } from "react";

interface VirtualTableProps<T> {
  /** Data rows */
  data: T[];
  /** Render function for each row */
  renderRow: (item: T, index: number) => React.ReactNode;
  /** Render function for header */
  renderHeader: () => React.ReactNode;
  /** Maximum rows per page (default 100) */
  maxRows?: number;
  /** Table class name */
  className?: string;
  /** Show row count info */
  showCount?: boolean;
  /** Empty state message */
  emptyMessage?: string;
}

export function VirtualTable<T>({
  data,
  renderRow,
  renderHeader,
  maxRows = 100,
  className = "",
  showCount = true,
  emptyMessage = "No data",
}: VirtualTableProps<T>) {
  const [page, setPage] = useState(0);

  const totalPages = Math.ceil(data.length / maxRows);
  const needsPagination = data.length > maxRows;

  const visibleData = useMemo(() => {
    if (!needsPagination) return data;
    const start = page * maxRows;
    return data.slice(start, start + maxRows);
  }, [data, page, maxRows, needsPagination]);

  const handlePrevPage = () => {
    setPage((p) => Math.max(0, p - 1));
  };

  const handleNextPage = () => {
    setPage((p) => Math.min(totalPages - 1, p + 1));
  };

  if (data.length === 0) {
    return (
      <div className={`virtual-table-empty ${className}`}>
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className={`virtual-table-container ${className}`}>
      {showCount && (
        <div className="virtual-table-info">
          {needsPagination ? (
            <span>
              Showing {page * maxRows + 1}-
              {Math.min((page + 1) * maxRows, data.length)} of {data.length}
            </span>
          ) : (
            <span>{data.length} rows</span>
          )}
        </div>
      )}

      <div className="virtual-table">
        {renderHeader()}
        {visibleData.map((item, index) => renderRow(item, page * maxRows + index))}
      </div>

      {needsPagination && (
        <div className="virtual-table-pagination">
          <button
            className="pagination-btn"
            onClick={handlePrevPage}
            disabled={page === 0}
          >
            Previous
          </button>
          <span className="pagination-info">
            Page {page + 1} of {totalPages}
          </span>
          <button
            className="pagination-btn"
            onClick={handleNextPage}
            disabled={page >= totalPages - 1}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
