import { createRoot } from 'react-dom/client'
import App from './App'
import { AuthProvider } from './auth'
import './styles.css'
import './auroom.css'
import './billing.css'

createRoot(document.getElementById('root')!).render(
  <AuthProvider><App /></AuthProvider>,
)
