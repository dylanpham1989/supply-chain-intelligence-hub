import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router'
import { AuthProvider } from './hooks/use-auth'
import { AppRoutes } from './routes'

const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // A 401 is handled by the refresh interceptor; retrying it here would
      // only multiply the failures.
      retry: (failureCount, error) =>
        failureCount < 2 && !String(error).includes('unauthenticated'),
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
