import React, { useState, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

// IMPORTURI PAGINI
import Detection from "./pages/Detection";
import Tracking from "./pages/Tracking";
import Dashboard from "./pages/Dashboard"; 
import Login from "./Login";
import Register from "./Register";
import WatchVideo from "./pages/WatchVideo";
import WatchImage from "./pages/WatchImage";
import History from "./pages/History";
import TrackingHistoryDetail from "./pages/TrackingHistoryDetail";

// IMPORT LAYOUT
import Layout from "./components/Layout";

// IMPORT AUTH CONTEXT
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { LanguageProvider } from "./contexts/LanguageContext";
import { ProcessingProvider } from "./contexts/ProcessingContext";

// Componentă wrapper pentru rute protejate
function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? children : <Navigate to="/login" replace />;
}

// Componentă wrapper pentru rute publice (redirect la dashboard dacă ești autentificat)
function PublicRoute({ children }) {
  const { isAuthenticated } = useAuth();
  return !isAuthenticated ? children : <Navigate to="/dashboard" replace />;
}

function AppContent() {
  const { login } = useAuth();

  // Funcție pentru login (trimisă către componenta Login)
  const handleLogin = (newToken, username) => {
    login(newToken, username);
  };

  return (
    <Routes>
      {/* === RUTE PUBLICE (Fără Sidebar) === */}
      <Route 
        path="/login" 
        element={
          <PublicRoute>
            <Login onLogin={handleLogin} />
          </PublicRoute>
        } 
      />
      <Route 
        path="/register" 
        element={
          <PublicRoute>
            <Register />
          </PublicRoute>
        } 
      />
      
      {/* Rută publică pentru vizionarea video-urilor procesate */}
      <Route 
        path="/watch/:videoId" 
        element={<WatchVideo />} 
      />
      <Route 
        path="/watch-image/:videoId" 
        element={<WatchImage />} 
      />

      {/* === RUTE PROTEJATE (Cu Sidebar Global) === */}
      <Route element={<Layout />}>
        <Route 
          path="/dashboard" 
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          } 
        />
        
        <Route 
          path="/detection" 
          element={
            <ProtectedRoute>
              <Detection />
            </ProtectedRoute>
          } 
        />
        
        <Route 
          path="/tracking" 
          element={
            <ProtectedRoute>
              <Tracking />
            </ProtectedRoute>
          } 
        />

        <Route
          path="/history"
          element={
            <ProtectedRoute>
              <History />
            </ProtectedRoute>
          }
        />

        <Route
          path="/tracking-history/:sessionId"
          element={
            <ProtectedRoute>
              <TrackingHistoryDetail />
            </ProtectedRoute>
          }
        />

        </Route>

      {/* Redirect root */}
      <Route 
        path="/" 
        element={<Navigate to="/dashboard" replace />} 
      />

      {/* Catch all - pentru pagini inexistente */}
      <Route path="*" element={<Navigate to="/login" replace />} />

    </Routes>
  );
}

function App() {
  return (
    <Router>
      <LanguageProvider>
        <AuthProvider>
          <ProcessingProvider>
            <AppContent />
          </ProcessingProvider>
        </AuthProvider>
      </LanguageProvider>
    </Router>
  );
}

export default App;
