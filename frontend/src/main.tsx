import { createRoot } from 'react-dom/client'
import App from './App'
import { AuthProvider } from './auth'
import './styles.css'
import './auroom.css'
import './billing.css'
import './admin.css'
import './ideas.css'
import './questionnaire.css'
import './create-questionnaire.css'
// Keep brand overrides last so questionnaire component styles cannot override the approved AuRoom palette.
import './brand.css'

createRoot(document.getElementById('root')!).render(
  <AuthProvider><App /></AuthProvider>,
)
