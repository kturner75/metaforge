import React from 'react'
import ReactDOM from 'react-dom/client'
import '@/components/styles' // Register presentation styles before App renders
import App from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
