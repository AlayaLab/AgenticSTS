import { ThemeProvider } from '@/theme/ThemeProvider'
import { Nav } from '@/components/shared/Nav'
import { Footer } from '@/components/shared/Footer'
import { Home } from '@/routes/Home'

export default function App() {
  return (
    <ThemeProvider>
      <div className="min-h-screen bg-[color:var(--color-bg-base)] text-[color:var(--color-ink-primary)]">
        <div
          role="alert"
          className="w-full bg-[color:var(--color-danger)] px-4 py-2 text-center font-body text-sm font-semibold text-white"
        >
          DEMO / MOCK DATA — illustrative only; not the paper's results. See the paper and dataset for real numbers.
        </div>
        <Nav />
        <main>
          <Home />
        </main>
        <Footer />
      </div>
    </ThemeProvider>
  )
}
