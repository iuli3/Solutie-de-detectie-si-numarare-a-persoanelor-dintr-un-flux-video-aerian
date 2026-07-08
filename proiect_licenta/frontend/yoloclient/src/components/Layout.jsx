import React, { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./SideBar";

const Layout = () => {
  // 1. Starea e acum AICI (în părinte)
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="min-h-screen text-zinc-100 font-sans flex">
      
      {/* 2. Trimitem starea și funcția de modificare la Sidebar */}
      <Sidebar isExpanded={isExpanded} setIsExpanded={setIsExpanded} />

      {/* 3. Containerul paginii se adaptează dinamic */}
      {/* Dacă e expandat -> padding 64 (256px). Dacă e strâns -> padding 20 (80px) */}
      <div 
        className={`flex-1 w-full min-h-screen pb-20 md:pb-0 transition-all duration-300 ease-in-out
          ${isExpanded ? "md:pl-64" : "md:pl-20"}`}
      >
        <Outlet />
      </div>

    </div>
  );
};

export default Layout;
