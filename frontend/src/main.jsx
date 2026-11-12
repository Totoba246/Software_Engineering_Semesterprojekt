/*
 * START OF THE WEB PAGE (the first of our files the browser runs)
 *
 * index.html contains an empty <div id="root">. This file puts our React app
 * (App.jsx) into it. React = a library that builds the page out of small
 * reusable pieces ("components") and redraws them when data changes.
 *
 * BrowserRouter makes addresses like /geraete/101 work without reloading the page.
 * The CSS files give the page its look (styles.css = our colors and layout,
 * leaflet.css = the map).
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import 'leaflet/dist/leaflet.css'
import './styles.css'
import App from './App.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
