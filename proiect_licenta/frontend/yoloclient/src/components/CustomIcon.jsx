import React from 'react';

const MyIcon = ({ size = 24, className = "" }) => {
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 24 24" // Verifică viewBox-ul original al SVG-ului tău
            fill="none"
            stroke="currentColor" // Face ca iconița să asculte de clasele Tailwind (ex: text-lime-400)
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={className}
        >
            {/* Aici lipești PATH-urile din fișierul tău SVG */}
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
        </svg>
    );
};

export default MyIcon;