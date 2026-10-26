export function MarketIllustration() {
  return (
    <svg aria-hidden="true" className="market-illustration" fill="none" viewBox="0 0 460 280">
      <defs>
        <linearGradient id="market-glow" x1="55" x2="390" y1="25" y2="256">
          <stop stopColor="#FFFFFF" stopOpacity=".92" />
          <stop offset="1" stopColor="#DCEAFF" stopOpacity=".7" />
        </linearGradient>
        <linearGradient id="market-core" x1="199" x2="267" y1="104" y2="178">
          <stop stopColor="#75A7FF" />
          <stop offset="1" stopColor="#376DE2" />
        </linearGradient>
        <filter id="market-shadow" x="-30%" y="-30%" width="160%" height="170%">
          <feDropShadow dx="0" dy="12" floodColor="#4168AA" floodOpacity=".15" stdDeviation="12" />
        </filter>
      </defs>
      <circle cx="230" cy="140" r="118" fill="url(#market-glow)" />
      <circle cx="230" cy="140" r="88" stroke="#BBD2F8" strokeDasharray="3 7" />
      <path
        d="M102 143c34-43 70-64 108-64 47 0 73 54 111 54 20 0 37-10 52-30"
        stroke="#B9D0F5"
        strokeWidth="1.5"
      />
      <path
        d="M119 203c32-30 68-45 107-45 47 0 64 24 105 24 22 0 41-7 58-21"
        stroke="#D0DFF8"
        strokeWidth="1.5"
      />
      <g filter="url(#market-shadow)">
        <rect x="171" y="88" width="118" height="104" rx="24" fill="url(#market-core)" />
        <path
          d="m229.5 111 7.2 22.3 22.3 7.2-22.3 7.2-7.2 22.3-7.2-22.3-22.3-7.2 22.3-7.2 7.2-22.3Z"
          fill="white"
          fillOpacity=".94"
        />
        <circle cx="260" cy="112" r="4" fill="#DCEAFF" />
        <circle cx="202" cy="165" r="3" fill="#DCEAFF" />
      </g>
      <g filter="url(#market-shadow)">
        <rect x="56" y="89" width="105" height="59" rx="15" fill="white" />
        <rect x="70" y="103" width="28" height="29" rx="9" fill="#EAF2FF" />
        <path
          d="M79 112h10m-5-5v10m-3.5-10 7 10m0-10-7 10"
          stroke="#4B82E9"
          strokeLinecap="round"
          strokeWidth="1.4"
        />
        <rect x="106" y="106" width="40" height="5" rx="2.5" fill="#C9D8EF" />
        <rect x="106" y="117" width="31" height="4" rx="2" fill="#E0E8F4" />
      </g>
      <g filter="url(#market-shadow)">
        <rect x="300" y="170" width="110" height="61" rx="16" fill="white" />
        <rect x="314" y="184" width="29" height="31" rx="9" fill="#EAF8F5" />
        <path
          d="M320 207v-9m6 9v-15m6 15v-12"
          stroke="#47A98A"
          strokeLinecap="round"
          strokeWidth="2"
        />
        <rect x="352" y="187" width="43" height="5" rx="2.5" fill="#C9D8EF" />
        <rect x="352" y="198" width="32" height="4" rx="2" fill="#E0E8F4" />
      </g>
      <circle cx="351" cy="70" r="13" fill="#FFF" />
      <path
        d="m351 62 2.4 6.2 6.1 2.3-6.1 2.4-2.4 6.1-2.3-6.1-6.2-2.4 6.2-2.3L351 62Z"
        fill="#78A5F2"
      />
      <circle cx="108" cy="188" r="5" fill="#89B5FD" />
      <circle cx="376" cy="119" r="4" fill="#8BD4C0" />
      <circle cx="180" cy="48" r="3" fill="#89B5FD" />
    </svg>
  );
}
