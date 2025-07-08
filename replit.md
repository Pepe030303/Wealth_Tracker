# 투자 포트폴리오 관리 시스템

## Overview

This is a Flask-based investment portfolio management web application that provides real-time stock price monitoring, dividend tracking, and portfolio analysis. The system allows users to manage their investment holdings, track dividends, and visualize portfolio allocation through interactive charts.

## System Architecture

### Backend Architecture
- **Flask Framework**: Core web application framework with blueprint-based routing
- **SQLAlchemy ORM**: Database abstraction layer with declarative base model
- **SQLite Database**: Lightweight relational database for data persistence
- **Multi-API Stock Service**: Robust stock price fetching with multiple API providers and caching

### Frontend Architecture
- **Server-Side Rendering**: Traditional Flask template rendering with Jinja2
- **Bootstrap 5**: Responsive UI framework with dark theme
- **Chart.js**: Interactive charts for data visualization
- **Vanilla JavaScript**: Client-side functionality without heavy frameworks

### Database Design
Four main entities:
1. **Trade**: All buy/sell transaction records (symbol, trade_type, quantity, price, trade_date)
2. **Holding**: Investment positions calculated from trades (symbol, quantity, purchase_price, dates)
3. **Dividend**: Dividend payment records (symbol, amount, dividend_date)
4. **StockPrice**: Cached stock prices with change tracking (symbol, current_price, change, last_updated)

## Key Components

### Stock API Service (`stock_api.py`)
- **Multi-Provider Support**: Alpha Vantage, IEX Cloud, Finnhub, Yahoo Finance
- **Intelligent Caching**: 5-minute cache to reduce API calls
- **Fallback Strategy**: Graceful degradation between API providers
- **Error Handling**: Comprehensive error handling with logging

### Route Management (`routes.py`)
- **Dashboard**: Portfolio overview with real-time calculations
- **Trade Management**: Manual buy/sell transaction recording with FIFO calculations
- **Holdings Management**: Auto-calculated from trade records (read-only display)
- **Dividend Tracking**: Dividend record management with monthly aggregation
- **Portfolio Allocation**: Asset allocation analysis and visualization

### Database Models (`models.py`)
- **Trade Model**: Records all buy/sell transactions with FIFO validation
- **Holding Model**: Auto-calculated from trades using FIFO accounting
- **Dividend Model**: Records dividend payments with date tracking
- **StockPrice Model**: Caches real-time price data with change metrics

### Trade Management System
- **Manual Transaction Entry**: Users input buy/sell records from spreadsheets
- **FIFO Calculations**: First-in-first-out accounting for accurate cost basis
- **Sell Validation**: Prevents overselling by checking available quantities
- **Auto Holdings Sync**: Recalculates holdings after each trade modification

## Data Flow

1. **Stock Price Updates**: 
   - Check cache first (5-minute TTL)
   - Fetch from primary API provider
   - Fallback to secondary providers on failure
   - Update cache with new data

2. **Portfolio Calculations**:
   - Aggregate holdings data
   - Fetch current prices for all symbols
   - Calculate profit/loss, returns, and allocation percentages
   - Update dashboard metrics in real-time

3. **Dividend Processing**:
   - Record dividend payments with dates
   - Aggregate monthly totals for chart visualization
   - Track dividend history per symbol

## External Dependencies

### Stock Market APIs
- **Alpha Vantage**: Primary stock price provider
- **IEX Cloud**: Secondary stock price provider
- **Finnhub**: Alternative stock data source
- **Yahoo Finance**: Free fallback option

### Frontend Libraries
- **Bootstrap 5**: UI framework with dark theme support
- **Chart.js**: Chart rendering for dividends and allocation
- **Font Awesome**: Icon library for UI elements

### Python Dependencies
- **Flask**: Web framework
- **Flask-SQLAlchemy**: ORM integration
- **Requests**: HTTP client for API calls
- **Python-dotenv**: Environment variable management

## Deployment Strategy

### Environment Configuration
- Environment variables for API keys and database URLs
- Production-ready WSGI configuration with ProxyFix
- SQLite for development, easily upgradeable to PostgreSQL

### Application Structure
- **main.py**: Application entry point
- **app.py**: Flask application factory with database initialization
- **models.py**: Database schema definitions
- **routes.py**: Request handling and business logic
- **stock_api.py**: External API integration

### Security Considerations
- Session secret key from environment variables
- API key management through environment variables
- SQL injection protection through SQLAlchemy ORM

## Changelog

Changelog:
- July 08, 2025. Initial setup with basic portfolio tracking
- July 08, 2025. Added trade-based holdings management system with FIFO calculations
- July 08, 2025. Enhanced dividend system with yield calculations, expected annual dividends, and dividend allocation visualization
- July 08, 2025. Implemented modern UI enhancements with fixed navbar, stock logos via Clearbit API, dividend month indicators, and enhanced card-based layouts with gradient styling

## User Preferences

Preferred communication style: Simple, everyday language.