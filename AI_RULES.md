# AI Development Rules - Shopee Video Counter

## Tech Stack
*   **Frontend Framework**: React 18 with TypeScript for robust type safety and component-based architecture.
*   **Build Tooling**: Vite for ultra-fast development server and optimized production builds.
*   **Styling**: Tailwind CSS for utility-first, responsive, and maintainable UI design.
*   **Icons**: Lucide React for a consistent and lightweight iconography set.
*   **Routing**: React Router DOM for managing client-side navigation.
*   **Scraping Engine**: Python 3.10+ with Playwright for high-performance browser automation and anti-detection.
*   **Asynchronous Logic**: Python `asyncio` for handling concurrent scraping tasks and rate limiting.
*   **Data Persistence**: JSON and CSV formats for scraper outputs and session cookie management.

## Library & Implementation Rules

### Frontend
*   **Styling**: Use **Tailwind CSS** exclusively for all layout and component styling. Avoid writing raw CSS in `.css` files.
*   **Components**: Prioritize **shadcn/ui** patterns for complex components (Modals, Tables, Inputs). Keep components small (under 100 lines) and focused.
*   **Icons**: Always use **Lucide React**. Do not introduce other icon libraries.
*   **State**: Use React hooks (`useState`, `useMemo`, `useCallback`) for local state. Only introduce global state libraries if complexity warrants it.

### Backend (Scraper)
*   **Automation**: Use **Playwright** for all interactions with the Shopee web interface.
*   **Concurrency**: Always use `async/await` patterns with `asyncio`. Maintain a `RateLimiter` to avoid IP bans.
*   **Resilience**: Implement exponential backoff retries for network-heavy operations.
*   **Logging**: Use the standard Python `logging` module with both file and console handlers.

### General
*   **Type Safety**: All new frontend code must be written in **TypeScript**. Avoid `any` types.
*   **File Structure**: Keep logic separated: `src/pages` for views, `src/components` for reusable UI, and root-level `.py` files for scraping utilities.