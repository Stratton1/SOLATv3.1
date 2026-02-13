# IG Broker EPIC Mapping (v3.1)

This document tracks the mapping between SOLAT internal symbols and IG Broker EPICs for both DEMO and LIVE environments.

## Forex (Major Pairs)

| Symbol | IG Instrument Name | DEMO EPIC | LIVE EPIC | Pip Size |
| :--- | :--- | :--- | :--- | :--- |
| EURUSD | Euro/US Dollar | CS.D.EURUSD.MINI.IP | CS.D.EURUSD.TODAY.IP | 0.0001 |
| GBPUSD | GBP/US Dollar | CS.D.GBPUSD.MINI.IP | CS.D.GBPUSD.TODAY.IP | 0.0001 |
| USDJPY | US Dollar/Japanese Yen | CS.D.USDJPY.MINI.IP | CS.D.USDJPY.TODAY.IP | 0.01 |
| USDCHF | US Dollar/Swiss Franc | CS.D.USDCHF.MINI.IP | CS.D.USDCHF.TODAY.IP | 0.0001 |
| AUDUSD | Australian Dollar/US Dollar | CS.D.AUDUSD.MINI.IP | CS.D.AUDUSD.TODAY.IP | 0.0001 |
| USDCAD | US Dollar/Canadian Dollar | CS.D.USDCAD.MINI.IP | CS.D.USDCAD.TODAY.IP | 0.0001 |
| NZDUSD | New Zealand Dollar/US Dollar | CS.D.NZDUSD.MINI.IP | CS.D.NZDUSD.TODAY.IP | 0.0001 |
| EURGBP | Euro/British Pound | CS.D.EURGBP.MINI.IP | CS.D.EURGBP.TODAY.IP | 0.0001 |
| EURJPY | Euro/Japanese Yen | CS.D.EURJPY.MINI.IP | CS.D.EURJPY.TODAY.IP | 0.01 |
| GBPJPY | British Pound/Japanese Yen | CS.D.GBPJPY.MINI.IP | CS.D.GBPJPY.TODAY.IP | 0.01 |

## Indices (Major)

| Symbol | IG Instrument Name | DEMO EPIC | LIVE EPIC | Pip Size |
| :--- | :--- | :--- | :--- | :--- |
| US500 | US 500 (S&P 500) | IX.D.SPTRD.IFD.IP | IX.D.SPTRD.IFD.IP | 0.1 |
| NAS100 | US Tech 100 (Nasdaq) | IX.D.NASDAQ.IFD.IP | IX.D.NASDAQ.IFD.IP | 0.1 |
| US30 | Wall Street (Dow Jones) | IX.D.DOW.IFD.IP | IX.D.DOW.IFD.IP | 1.0 |
| GER40 | Germany 40 (DAX) | IX.D.DAX.IFD.IP | IX.D.DAX.IFD.IP | 0.1 |
| UK100 | UK 100 (FTSE) | IX.D.FTSE.CFD.IP | IX.D.FTSE.CFD.IP | 0.1 |
| FRA40 | France 40 (CAC) | IX.D.CAC.IFD.IP | IX.D.CAC.IFD.IP | 0.1 |
| JP225 | Japan 225 (Nikkei) | IX.D.NIKKEI.IFD.IP | IX.D.NIKKEI.IFD.IP | 1.0 |
| AUS200 | Australia 200 | IX.D.ASX.IFD.IP | IX.D.ASX.IFD.IP | 0.1 |

*Note: Indices often share EPICs between DEMO and LIVE, but verification is required on the LIVE platform.*

## Commodities

| Symbol | IG Instrument Name | DEMO EPIC | LIVE EPIC | Pip Size |
| :--- | :--- | :--- | :--- | :--- |
| XAUUSD | Gold | CC.D.GOLD.USS.IP | CC.D.GOLD.USS.IP | 0.01 |
| XAGUSD | Silver | CC.D.SILVER.USS.IP | CC.D.SILVER.USS.IP | 0.001 |
| USOIL | US Crude Oil | CC.D.WTI.USS.IP | CC.D.WTI.USS.IP | 0.01 |
| UKOIL | Brent Crude Oil | CC.D.BRENT.USS.IP | CC.D.BRENT.USS.IP | 0.01 |

## Status
- Forex mapping: **Verified** (Seed data updated)
- Indices mapping: **Pending Verification** (Values from existing `instruments.json`)
- Commodities mapping: **Draft** (Common patterns used)
