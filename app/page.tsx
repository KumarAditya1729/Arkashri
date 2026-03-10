'use client'

import { useEffect, useState } from 'react'

export default function Home() {
  const [message, setMessage] = useState('Loading...')

  useEffect(() => {
    // Test API connection
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://arkashri-production.up.railway.app'}/`)
      .then(res => res.json())
      .then(data => setMessage(`✅ Backend Connected: ${JSON.stringify(data)}`))
      .catch(err => setMessage(`❌ Error: ${err.message}`))
  }, [])

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      <h1>🎉 Arkashri Audit OS</h1>
      <h2>Enterprise Audit Platform</h2>
      <div style={{
        background: '#f0f9ff',
        padding: '20px',
        borderRadius: '8px',
        marginTop: '20px'
      }}>
        <h3>🚀 Backend Status</h3>
        <p>{message}</p>
        <p><strong>Frontend URL:</strong> {process.env.NEXT_PUBLIC_API_URL}</p>
        <p><strong>Backend URL:</strong> https://arkashri-production.up.railway.app</p>
      </div>
    </div>
  )
}
