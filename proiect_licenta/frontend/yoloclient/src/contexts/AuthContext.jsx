import React, { createContext, useContext, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [user, setUser] = useState(localStorage.getItem("user"));
  
  // Funcție pentru decodarea JWT
  const decodeToken = (token) => {
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const jsonPayload = decodeURIComponent(atob(base64).split('').map((c) => {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(''));
      return JSON.parse(jsonPayload);
    } catch (error) {
      return null;
    }
  };

  // Verificare validitate token
  const isTokenValid = (token) => {
    if (!token) return false;
    const decoded = decodeToken(token);
    if (!decoded || !decoded.exp) return false;
    const currentTime = Date.now() / 1000;
    return decoded.exp > currentTime;
  };

  // Funcție de login
  const login = (newToken, newUser) => {
    localStorage.setItem("token", newToken);
    localStorage.setItem("user", newUser);
    setToken(newToken);
    setUser(newUser);
  };

  // Funcție de logout cu cleanup complet
  const logout = () => {
    // Emit eveniment custom pentru ca toate componentele să facă cleanup
    window.dispatchEvent(new CustomEvent("user-logout"));
    
    // Așteptăm puțin pentru ca componente să facă cleanup
    setTimeout(() => {
      // Curățăm localStorage
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      
      // Resetăm state-ul
      setToken(null);
      setUser(null);
      
      // Navigarea va fi făcută de componenta care apelează logout
      console.log("✅ Logout complet - toate resursele au fost eliberate");
    }, 100);
  };

  // Verificare periodică a tokenului
  useEffect(() => {
    if (token && !isTokenValid(token)) {
      logout();
      return;
    }

    const interval = setInterval(() => {
      const currentToken = localStorage.getItem("token");
      if (currentToken && !isTokenValid(currentToken)) {
        logout();
      }
    }, 30000); // verificare la 30 secunde

    return () => clearInterval(interval);
  }, [token]);

  const value = {
    token,
    user,
    login,
    logout,
    isAuthenticated: !!token && isTokenValid(token)
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// Hook personalizat pentru a folosi contextul
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth trebuie folosit în interiorul AuthProvider");
  }
  return context;
};
