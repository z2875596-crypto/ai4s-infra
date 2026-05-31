const sizes = { small: 32, medium: 40, large: 48 };

export default function Logo({ size = "medium" }: { size?: "small" | "medium" | "large" }) {
  const px = sizes[size];

  return (
    <svg width={px} height={px} viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
      <polygon points="88,50 69,83 31,83 12,50 31,17 69,17" fill="#EEF2FF" stroke="#4F46E5" strokeWidth="1.5" />
      <polygon points="70,50 60,67 40,67 30,50 40,33 60,33" fill="none" stroke="#4F46E5" strokeWidth="1.5" />
      <line x1="88" y1="50" x2="70" y2="50" stroke="#4F46E5" strokeWidth="1.5" />
      <line x1="69" y1="83" x2="60" y2="67" stroke="#4F46E5" strokeWidth="1.5" />
      <line x1="31" y1="83" x2="40" y2="67" stroke="#4F46E5" strokeWidth="1.5" />
      <line x1="12" y1="50" x2="30" y2="50" stroke="#4F46E5" strokeWidth="1.5" />
      <line x1="31" y1="17" x2="40" y2="33" stroke="#4F46E5" strokeWidth="1.5" />
      <line x1="69" y1="17" x2="60" y2="33" stroke="#4F46E5" strokeWidth="1.5" />
      <circle cx="50" cy="50" r="8" fill="#4F46E5" />
      <ellipse cx="50" cy="44" rx="3" ry="7" fill="white" />
      <ellipse cx="50" cy="44" rx="3" ry="7" fill="white" transform="rotate(120 50 50)" />
      <ellipse cx="50" cy="44" rx="3" ry="7" fill="white" transform="rotate(240 50 50)" />
    </svg>
  );
}
