import React, { useState } from 'react';
import {
  GlobeWebIcon,
  TerminalIcon,
  ServerIcon,
  CpuChipIcon,
  AppsTabIcon,
  ShieldIcon,
} from '../icons/Icons';

export interface AppLogoProps {
  app: {
    id?: string;
    name?: string;
    processName?: string;
    category?: string;
    iconType?: string;
    iconDataUrl?: string;
  };
  size?: number;
  className?: string;
}

// ==========================================
// 1. BRAND VECTOR LOGO SVGS
// ==========================================

/* Google Chrome (Authentic 4-color) */
export const ChromeLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="24" r="20" fill="#ffffff" />
    <path d="M24 4C14.06 4 5.8 11.24 4.25 20.73L13.8 37.28A20 20 0 0 1 24 4Z" fill="#EA4335" />
    <path d="M43.75 20.73C42.2 11.24 33.94 4 24 4l9.55 16.54h10.2z" fill="#FBBC05" />
    <path d="M24 44c9.94 0 18.2-7.24 19.75-16.73H24.2l-9.55 16.54C17.65 43.8 20.73 44 24 44Z" fill="#34A853" />
    <circle cx="24" cy="24" r="9.5" fill="#ffffff" />
    <circle cx="24" cy="24" r="7.5" fill="#1A73E8" />
  </svg>
);

/* Microsoft Edge (Authentic Gradient Swirl) */
export const EdgeLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <defs>
      <linearGradient id="edgeGrad1" x1="12" y1="36" x2="36" y2="12" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#0c59a4" />
        <stop offset="100%" stopColor="#11b5e4" />
      </linearGradient>
      <linearGradient id="edgeGrad2" x1="4" y1="24" x2="24" y2="44" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#0078d4" />
        <stop offset="100%" stopColor="#00bcf2" />
      </linearGradient>
      <linearGradient id="edgeGrad3" x1="24" y1="4" x2="44" y2="24" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#40c4ff" />
        <stop offset="100%" stopColor="#50e3c2" />
      </linearGradient>
    </defs>
    <path d="M42.8 32.5c-.8 5.6-5.8 9.5-12.8 9.5-8.8 0-16-7.2-16-16 0-1.8.3-3.6.9-5.2C13 18.3 12 15.7 12 13c0-4.9 3.5-9 8.4-9.8 1.1-.2 2.3-.2 3.6 0 7.8 1.2 13.5 7.8 13.5 15.8 0 1.2-.2 2.4-.5 3.5H23.5c-3.6 0-6.5 2.9-6.5 6.5s2.9 6.5 6.5 6.5h19.3z" fill="url(#edgeGrad1)" opacity="0.9" />
    <path d="M23.5 42C13.8 42 6 34.2 6 24.5c0-4.8 1.9-9.1 5-12.3 1.2 2.8 3.5 5.1 6.5 6.3-1.5 2.1-2.5 4.7-2.5 7.5 0 6.6 5.4 12 12 12 3.2 0 6.1-1.3 8.3-3.4-3.1 4.5-7.2 7.4-11.8 7.4z" fill="url(#edgeGrad2)" />
    <path d="M41 24.5c0-8.6-6.4-15.5-14.7-16.4 4.5 1.5 7.7 5.7 7.7 10.9 0 2.2-.6 4.3-1.7 6.1l9.1-.1c-.2-.2-.4-.3-.4-.5z" fill="url(#edgeGrad3)" />
  </svg>
);

/* Brave Browser (Authentic Lion Shield) */
export const BraveLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <path d="M24 4L7 11.5v12.7c0 10.9 7.3 21.1 17 23.8 9.7-2.7 17-12.9 17-23.8V11.5L24 4Z" fill="#FB542B" />
    <path d="M24 8l11.5 5.2v8.5c0 7.3-4.9 14.1-11.5 15.9-6.6-1.8-11.5-8.6-11.5-15.9v-8.5L24 8Z" fill="#FF7A00" />
    <circle cx="18.5" cy="20" r="2.2" fill="#ffffff" />
    <circle cx="29.5" cy="20" r="2.2" fill="#ffffff" />
    <path d="M24 24.5l-3.5 3.5h7L24 24.5Z" fill="#ffffff" />
    <path d="M19 31c1.5 1.5 3.2 2.2 5 2.2s3.5-.7 5-2.2" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

/* Mozilla Firefox (Flame Fox & Globe) */
export const FirefoxLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="24" r="18" fill="#3B2A70" />
    <circle cx="24" cy="24" r="14" fill="#662D91" opacity="0.8" />
    <path d="M40 20c0 9.9-8.1 18-18 18-4.5 0-8.6-1.7-11.7-4.5 4.5 1.5 9.7.5 13.2-2.5 3.8-3.3 4.5-8.8 2-12.8-1.2-2-3.1-3.5-5.5-4.2 3.8-1.5 8.2-1 11.5 1.2 5.2 3.5 8.5 8.8 8.5 14.8Z" fill="#FF7139" />
    <path d="M37 16c-1.5-4-5-7-9.5-8 3 1.5 5.5 4 6.5 7.2.8 2.5.5 5.3-.8 7.5 2.2-1.8 3.5-4.2 3.8-6.7Z" fill="#FFD43B" />
  </svg>
);

/* Visual Studio Code (Blue Ribbon) */
export const VsCodeLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
    <path d="M74.5 97.4L98.7 85.6c1.3-.6 2.1-1.9 2.1-3.3V17.7c0-1.4-.8-2.7-2.1-3.3L74.5 2.6c-1.4-.7-3.1-.4-4.2.7L28.1 40.8 12.4 28.8c-1-.8-2.4-.9-3.5-.3L1.5 32.7c-1.3.7-2 2-2 3.4v27.8c0 1.4.7 2.7 2 3.4l7.4 4.2c1.1.6 2.5.5 3.5-.3l15.7-12 42.2 37.5c1.1 1.1 2.8 1.4 4.2.7z" fill="#007ACC" />
    <path d="M74.5 2.6L34.2 39.4l40.3 36.8V2.6z" fill="#1F8AD2" />
    <path d="M98.7 14.4L74.5 2.6v94.8l24.2-11.8c1.3-.6 2.1-1.9 2.1-3.3V17.7c0-1.4-.8-2.7-2.1-3.3z" fill="#0065A9" />
    <path d="M28.1 40.8L1.5 61.2V38.8l26.6 2z" fill="#007ACC" opacity="0.85" />
  </svg>
);

/* Visual Studio Full IDE (Purple Infinity) */
export const VisualStudioLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <path d="M35 44l10-6c.6-.4 1-1 1-1.7V11.7c0-.7-.4-1.3-1-1.7L35 4c-.7-.4-1.5-.2-2 .4L16 20.5 7 13.5c-.5-.4-1.2-.5-1.7-.2L1 16c-.6.4-1 1-1 1.7v12.6c0 .7.4 1.3 1 1.7l4.3 2.7c.5.3 1.2.2 1.7-.2l9-7 17 16.1c.5.6 1.3.8 2 .4z" fill="#5C2D91" />
    <path d="M35 4l-18 17 18 16.5V4z" fill="#80397B" />
    <path d="M46 11.7L35 4v40l11-7.7V11.7z" fill="#3B1768" />
  </svg>
);

/* Discord (Blurple Controller Face) */
export const DiscordLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="10" fill="#5865F2" />
    <path d="M35.2 14.4c-2.4-1.1-5-1.9-7.7-2.4-.3.6-.7 1.4-.9 2-2.9-.4-5.8-.4-8.6 0-.3-.6-.6-1.4-.9-2-2.7.5-5.3 1.3-7.7 2.4-4.8 7.1-6.1 14-5.5 20.8 3.2 2.4 6.3 3.8 9.3 4.7 1-.9 1.9-1.9 2.7-3-1.1-.4-2.1-.9-3.1-1.6.3-.2.5-.4.8-.6 6.1 2.8 12.7 2.8 18.7 0 .3.2.5.4.8.6-1 .7-2 1.2-3.1 1.6.8 1.1 1.7 2.1 2.7 3 3-.9 6.1-2.3 9.3-4.7.7-7.9-.9-14.7-5.4-20.8zM18.8 28.5c-1.8 0-3.3-1.6-3.3-3.6s1.4-3.6 3.3-3.6 3.3 1.6 3.3 3.6-1.4 3.6-3.3 3.6zm10.4 0c-1.8 0-3.3-1.6-3.3-3.6s1.4-3.6 3.3-3.6 3.3 1.6 3.3 3.6-1.5 3.6-3.3 3.6z" fill="#ffffff" />
  </svg>
);

/* Slack (4-Color Hashtag) */
export const SlackLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="10" fill="#ffffff" />
    <path d="M14.5 27a3.5 3.5 0 1 1-3.5-3.5h3.5v3.5zm2 0a3.5 3.5 0 0 1 7 0v8.5a3.5 3.5 0 1 1-7 0V27z" fill="#E01E5A" />
    <path d="M21 14.5a3.5 3.5 0 1 1-3.5-3.5v3.5H21zm0 2a3.5 3.5 0 0 1 0 7H12.5a3.5 3.5 0 1 1 0-7H21z" fill="#36C5F0" />
    <path d="M33.5 21a3.5 3.5 0 1 1 3.5 3.5h-3.5V21zm-2 0a3.5 3.5 0 0 1-7 0v-8.5a3.5 3.5 0 1 1 7 0V21z" fill="#2EB67D" />
    <path d="M27 33.5a3.5 3.5 0 1 1 3.5 3.5H27v-3.5zm0-2a3.5 3.5 0 0 1 0-7h8.5a3.5 3.5 0 1 1 0 7H27z" fill="#ECB22E" />
  </svg>
);

/* Spotify (Neon Green Circle with Waves) */
export const SpotifyLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="24" r="22" fill="#1DB954" />
    <path d="M33.5 31.2c-.4.6-1.2.8-1.8.4-5-3-11.2-3.7-18.6-2-1 .2-1.3-.6-1.1-1.3.2-.7.8-1.2 1.5-1.3 8.1-1.8 15-.9 20.6 2.4.6.4.8 1.2.4 1.8zm2.6-5.8c-.5.8-1.5 1-2.3.5-5.8-3.5-14.6-4.5-21.4-2.4-.9.3-1.8-.2-2.1-1.1-.3-.9.2-1.8 1.1-2.1 7.8-2.4 17.5-1.2 24.2 2.8.8.5 1 1.5.5 2.3zm.3-6.1c-6.9-4.1-18.3-4.5-24.9-2.5-1 .3-2.1-.3-2.4-1.3-.3-1 .3-2.1 1.3-2.4 7.6-2.3 20.2-1.8 28.2 2.9 1 .6 1.3 1.8.7 2.7-.6.9-1.8 1.2-2.9.6z" fill="#121212" />
  </svg>
);

/* Docker (Blue Whale & Shipping Containers) */
export const DockerLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <path d="M46.8 21.8c-.8-.6-2.5-.8-3.8-.5-.3-1.9-1.6-3.4-3.5-4-.5-.1-1.1-.2-1.7-.1-.9-2.4-3.1-4-5.7-4-1.2 0-2.4.4-3.4 1.1-.1 0-.2-.1-.3-.1H5.3c-.7 0-1.3.6-1.3 1.3v2c0 3.3 1.3 6.4 3.7 8.7 3.3 3.2 8 5.1 13.1 5.1 8.8 0 16.5-5.4 19.3-13.4 2.3.2 4.6-.2 6.3-1.6.4-.3.6-.7.7-1.1.1-.5-.1-1.1-.6-1.4z" fill="#0db7ed" />
    <rect x="9" y="19" width="4" height="4" rx="0.5" fill="#0db7ed" />
    <rect x="14" y="19" width="4" height="4" rx="0.5" fill="#0db7ed" />
    <rect x="19" y="19" width="4" height="4" rx="0.5" fill="#0db7ed" />
    <rect x="14" y="14" width="4" height="4" rx="0.5" fill="#0db7ed" />
    <rect x="19" y="14" width="4" height="4" rx="0.5" fill="#0db7ed" />
    <rect x="24" y="14" width="4" height="4" rx="0.5" fill="#0db7ed" />
    <rect x="24" y="19" width="4" height="4" rx="0.5" fill="#0db7ed" />
    <rect x="19" y="9" width="4" height="4" rx="0.5" fill="#0db7ed" />
  </svg>
);

/* Python (Blue & Yellow Serpents) */
export const PythonLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <path d="M23.6 4c-9.8 0-9.2 4.2-9.2 4.2l.01 4.4h9.4v1.3H10.4S4 13.2 4 23.3s5.6 9.8 5.6 9.8h3.3v-4.7s-.2-5.6 5.5-5.6h9.5s5.3.1 5.3-5.2V8.7s.8-4.7-9.6-4.7zm-5.2 3a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8z" fill="#387EB8" />
    <path d="M24.4 44c9.8 0 9.2-4.2 9.2-4.2l-.01-4.4h-9.4v-1.3h13.4s6.4.7 6.4-9.4-5.6-9.8-5.6-9.8h-3.3v4.7s.2 5.6-5.5 5.6h-9.5s-5.3-.1-5.3 5.2v8.9s-.8 4.7 9.6 4.7zm5.2-3a1.4 1.4 0 1 1 0-2.8 1.4 1.4 0 0 1 0 2.8z" fill="#FFE052" />
  </svg>
);

/* Git (Orange Branch) */
export const GitLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <path d="M46.6 22.3L25.7 1.4c-1.8-1.8-4.8-1.8-6.6 0L1.4 19.1c-1.8 1.8-1.8 4.8 0 6.6l20.9 20.9c1.8 1.8 4.8 1.8 6.6 0l17.7-17.7c1.8-1.8 1.8-4.8 0-6.6z" fill="#F05032" />
    <circle cx="21" cy="27" r="3.5" fill="#ffffff" />
    <circle cx="31" cy="27" r="3.5" fill="#ffffff" />
    <circle cx="21" cy="14" r="3.5" fill="#ffffff" />
    <path d="M21 17.5v6M24.5 27h3" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

/* Ollama (Minimalist Llama Silhouette) */
export const OllamaLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="10" fill="#18181B" />
    <path d="M24 10l-4 6v8l-6 6v8h20v-8l-6-6v-8l-4-6Z" fill="#ffffff" />
    <circle cx="21" cy="18" r="1.5" fill="#18181B" />
    <circle cx="27" cy="18" r="1.5" fill="#18181B" />
  </svg>
);

/* Microsoft Word (Navy Blue 'W') */
export const WordLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect x="12" y="6" width="28" height="36" rx="4" fill="#2B579A" />
    <rect x="6" y="12" width="22" height="24" rx="3" fill="#185ABD" />
    <path d="M11 18h3l2.5 8 2.5-8h2.5l2.5 8 2.5-8h3l-3.5 12h-3l-2.5-7.5-2.5 7.5h-3L11 18Z" fill="#ffffff" />
  </svg>
);

/* Microsoft Excel (Forest Green 'X') */
export const ExcelLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect x="12" y="6" width="28" height="36" rx="4" fill="#217346" />
    <rect x="6" y="12" width="22" height="24" rx="3" fill="#107C41" />
    <path d="M12 18h3.5l3 5.5 3-5.5H25l-4.5 7.5L25 33h-3.5l-3-5.5-3 5.5H12l4.5-7.5L12 18Z" fill="#ffffff" />
  </svg>
);

/* Microsoft PowerPoint (Vermilion 'P') */
export const PowerPointLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect x="12" y="6" width="28" height="36" rx="4" fill="#D24726" />
    <rect x="6" y="12" width="22" height="24" rx="3" fill="#C43E1C" />
    <path d="M13 18h6.5c3 0 5 1.5 5 4s-2 4-5 4H16v7h-3V18zm3 6h3.5c1.2 0 2-.6 2-1.8s-.8-1.8-2-1.8H16V24z" fill="#ffffff" />
  </svg>
);

/* Microsoft OneNote (Purple 'N') */
export const OneNoteLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect x="12" y="6" width="28" height="36" rx="4" fill="#80397B" />
    <rect x="6" y="12" width="22" height="24" rx="3" fill="#7719AA" />
    <path d="M13 18h3.2l5.8 8.8V18H25v15h-3.2l-5.8-8.8V33H13V18Z" fill="#ffffff" />
  </svg>
);

/* Microsoft Teams (Purple 'T' and figures) */
export const TeamsLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="10" fill="#464EB8" />
    <circle cx="34" cy="18" r="4" fill="#7B83EB" />
    <path d="M28 26c0-3.3 2.7-6 6-6s6 2.7 6 6v4H28v-4z" fill="#7B83EB" />
    <rect x="8" y="12" width="20" height="24" rx="3" fill="#5059C9" />
    <path d="M14 18h8v2.5h-2.7V30h-2.6v-9.5H14V18Z" fill="#ffffff" />
  </svg>
);

/* Microsoft Outlook (Blue 'O' and mail envelope) */
export const OutlookLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect x="12" y="8" width="28" height="32" rx="4" fill="#0072C6" />
    <path d="M16 14l10 8 10-8v18H16V14Z" fill="#28A8EA" />
    <rect x="6" y="12" width="20" height="24" rx="3" fill="#005A9E" />
    <circle cx="16" cy="24" r="5" stroke="#ffffff" strokeWidth="2.5" />
  </svg>
);

/* Notion (Minimalist 'N' Cube) */
export const NotionLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="10" fill="#000000" />
    <path d="M12 12h5l13 18.5V12h6v24h-5L18 17.5V36h-6V12Z" fill="#ffffff" />
  </svg>
);

/* Obsidian (Faceted Purple Crystal) */
export const ObsidianLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <path d="M24 4l12 10-5 24-7 6-7-6-5-24L24 4Z" fill="#6C31E3" />
    <path d="M24 4l12 10-12 14V4Z" fill="#8B5CF6" />
    <path d="M24 28l7 10-7 6-7-6 7-10Z" fill="#4C1D95" />
  </svg>
);

/* Postman (Orange Astronaut) */
export const PostmanLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="24" r="22" fill="#FF6C37" />
    <path d="M16 26l12-12 4 4-12 12-4-4Z" fill="#ffffff" />
    <circle cx="34" cy="14" r="3" fill="#ffffff" />
  </svg>
);

/* Blender 3D (Orange & Blue Aperture) */
export const BlenderLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="28" r="12" fill="#EA7600" />
    <circle cx="24" cy="28" r="6" fill="#225B99" />
    <path d="M24 8v10M12 16l8 6M36 16l-8 6" stroke="#EA7600" strokeWidth="4" strokeLinecap="round" />
  </svg>
);

/* Zoom (Blue Video Camera) */
export const ZoomLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="10" fill="#2D8CFF" />
    <rect x="10" y="16" width="18" height="16" rx="3" fill="#ffffff" />
    <polygon points="30,21 38,16 38,32 30,27" fill="#ffffff" />
  </svg>
);

/* Telegram (Sky Blue Paper Airplane) */
export const TelegramLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="24" r="22" fill="#2AABEE" />
    <path d="M11 23.5l25-10-5 24-8-6-4 4-1-6 13-11-16 8-5-3Z" fill="#ffffff" />
  </svg>
);

/* WhatsApp (Green Chat Bubble & Phone) */
export const WhatsAppLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="24" r="22" fill="#25D366" />
    <path d="M24 10a14 14 0 0 0-12 21.3L10 38l7-1.8A14 14 0 1 0 24 10Zm7 19.5c-.3.8-1.7 1.5-2.4 1.6-.6.1-1.4.2-4.5-1.1-3.7-1.5-6.1-5.3-6.3-5.5-.2-.3-1.5-2-1.5-3.8 0-1.8 1-2.7 1.3-3 .3-.4.8-.5 1.1-.5.3 0 .6 0 .8.1.3 0 .6.7.9 1.4.3.7 1 2.4 1.1 2.6.1.2.1.4 0 .6-.1.2-.2.4-.4.6-.2.2-.4.4-.6.6-.2.2-.4.4-.2.8.3.5 1.2 2 2.7 3.3 1.9 1.7 3.5 2.2 4 2.4.5.2.8.2 1.1-.1.3-.4 1.3-1.5 1.7-2 .3-.5.7-.4 1.1-.2.4.2 2.6 1.2 3 1.4.5.3.8.4.9.7.2.3.2 1.4-.1 2.2Z" fill="#ffffff" />
  </svg>
);

/* Steam (Valve Piston / Crank) */
export const SteamLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="24" r="22" fill="#171A21" />
    <circle cx="32" cy="18" r="6" stroke="#ffffff" strokeWidth="2.5" />
    <circle cx="16" cy="30" r="4" fill="#ffffff" />
    <path d="M30 22l-10 6" stroke="#ffffff" strokeWidth="3" />
  </svg>
);

/* VLC Media Player (Orange Traffic Cone) */
export const VlcLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <ellipse cx="24" cy="40" rx="16" ry="4" fill="#FF8800" />
    <polygon points="18,36 30,36 26,8 22,8" fill="#FF8800" />
    <polygon points="19,30 29,30 28,24 20,24" fill="#ffffff" />
    <polygon points="21,18 27,18 26,13 22,13" fill="#ffffff" />
  </svg>
);

/* Adobe Suite Badge */
export const AdobeLogo: React.FC<{ size?: number; label?: string; bg?: string; textCol?: string }> = ({
  size = 24,
  label = 'Ps',
  bg = '#001E36',
  textCol = '#31A8FF',
}) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="8" fill={bg} />
    <text x="24" y="32" fill={textCol} fontSize="20" fontWeight="bold" fontFamily="sans-serif" textAnchor="middle">
      {label}
    </text>
  </svg>
);

// ==========================================
// 2. WINDOWS CORE & SYSTEM LOGOS
// ==========================================

/* Windows 11 File Explorer (Yellow Folder + Blue Spine) */
export const FileExplorerLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <path d="M4 12a4 4 0 0 1 4-4h10l4 4h18a4 4 0 0 1 4 4v20a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V12Z" fill="#F0A500" />
    <rect x="4" y="16" width="40" height="24" rx="3" fill="#FFC83B" />
    <rect x="8" y="13" width="10" height="12" rx="2" fill="#0078D4" opacity="0.9" />
  </svg>
);

/* Windows 11 Task Manager (Teal Pulse Chart) */
export const TaskManagerLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="8" fill="#0E7A0D" />
    <path d="M8 24h7l4-12 7 24 5-16 4 8 5-4h4" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/* Windows Settings (Modern Gear) */
export const WindowsSettingsLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="8" fill="#0078D4" />
    <circle cx="24" cy="24" r="6" stroke="#ffffff" strokeWidth="3" />
    <path d="M24 10v4M24 34v4M10 24h4M34 24h4M14 14l3 3M31 31l3 3M14 34l3-3M31 17l3-3" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

/* Windows Terminal */
export const WindowsTerminalLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="8" fill="#201F1E" />
    <polyline points="12,18 20,24 12,30" stroke="#4CC2FF" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
    <line x1="24" y1="30" x2="34" y2="30" stroke="#4CC2FF" strokeWidth="3.5" strokeLinecap="round" />
  </svg>
);

/* Command Prompt (Classic Console) */
export const CommandPromptLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="6" fill="#000000" />
    <rect x="2" y="2" width="44" height="44" rx="5" stroke="#ffffff" strokeWidth="1.5" />
    <polyline points="10,16 18,22 10,28" stroke="#ffffff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    <line x1="22" y1="28" x2="32" y2="28" stroke="#ffffff" strokeWidth="2.5" strokeLinecap="round" />
  </svg>
);

/* Windows PowerShell */
export const PowerShellLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="8" fill="#012456" />
    <polygon points="12,14 26,24 12,34 16,34 30,24 16,14" fill="#ffffff" />
    <line x1="24" y1="34" x2="36" y2="34" stroke="#ffffff" strokeWidth="3.5" strokeLinecap="round" />
  </svg>
);

/* Registry Editor (regedit) */
export const RegistryEditorLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="8" fill="#1F4E79" />
    <rect x="10" y="20" width="12" height="12" rx="2" fill="#5B9BD5" stroke="#ffffff" strokeWidth="1.5" />
    <rect x="26" y="20" width="12" height="12" rx="2" fill="#5B9BD5" stroke="#ffffff" strokeWidth="1.5" />
    <rect x="18" y="10" width="12" height="12" rx="2" fill="#ED7D31" stroke="#ffffff" strokeWidth="1.5" />
  </svg>
);

/* Notepad (Blue Memo Pad with Pencil) */
export const NotepadLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect x="10" y="6" width="28" height="36" rx="4" fill="#0078D4" />
    <rect x="14" y="10" width="20" height="28" rx="2" fill="#ffffff" />
    <line x1="18" y1="16" x2="30" y2="16" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" />
    <line x1="18" y1="22" x2="30" y2="22" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" />
    <line x1="18" y1="28" x2="26" y2="28" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

/* Paint (Palette & Brush) */
export const PaintLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <ellipse cx="24" cy="24" rx="20" ry="16" fill="#F4F4F4" stroke="#d1d5db" strokeWidth="2" />
    <circle cx="15" cy="20" r="3" fill="#EA4335" />
    <circle cx="24" cy="15" r="3" fill="#FBBC05" />
    <circle cx="33" cy="20" r="3" fill="#34A853" />
    <circle cx="28" cy="29" r="3" fill="#1A73E8" />
    <path d="M12 30c3-1 6 1 6 3s-3 3-6 0z" fill="#9333EA" />
  </svg>
);

/* Calculator (Grid with Display) */
export const CalculatorLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect x="8" y="6" width="32" height="36" rx="6" fill="#0078D4" />
    <rect x="12" y="10" width="24" height="8" rx="2" fill="#E1DFDD" />
    <circle cx="16" cy="24" r="2.5" fill="#ffffff" />
    <circle cx="24" cy="24" r="2.5" fill="#ffffff" />
    <circle cx="32" cy="24" r="2.5" fill="#ffffff" />
    <circle cx="16" cy="32" r="2.5" fill="#ffffff" />
    <circle cx="24" cy="32" r="2.5" fill="#ffffff" />
    <circle cx="32" cy="32" r="2.5" fill="#FFB900" />
  </svg>
);

/* Snipping Tool (Scissors & Frame) */
export const SnippingToolLogo: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <rect width="48" height="48" rx="8" fill="#0078D4" />
    <circle cx="18" cy="30" r="4" stroke="#ffffff" strokeWidth="2" />
    <circle cx="30" cy="30" r="4" stroke="#ffffff" strokeWidth="2" />
    <line x1="20" y1="27" x2="30" y2="15" stroke="#ffffff" strokeWidth="2.5" strokeLinecap="round" />
    <line x1="28" y1="27" x2="18" y2="15" stroke="#ffffff" strokeWidth="2.5" strokeLinecap="round" />
  </svg>
);

// ==========================================
// 3. UNIVERSAL LOGO RESOLVER & COMPONENT
// ==========================================

export const AppLogoIcon: React.FC<AppLogoProps> = ({ app, size = 24, className }) => {
  const [imgError, setImgError] = useState(false);

  const name = (app?.name || '').toLowerCase();
  const proc = (app?.processName || '').toLowerCase();
  const id = (app?.id || '').toLowerCase();
  const cat = (app?.category || '').toLowerCase();

  // Tier 1: Match Vector Brand SVG
  // --- Web Browsers ---
  if (proc.includes('chrome') || name.includes('chrome') || id.includes('chrome')) return <ChromeLogo size={size} />;
  if (proc.includes('msedge') || proc.includes('edge') || name.includes('edge') || id.includes('edge')) return <EdgeLogo size={size} />;
  if (proc.includes('brave') || name.includes('brave') || id.includes('brave')) return <BraveLogo size={size} />;
  if (proc.includes('firefox') || name.includes('firefox') || id.includes('firefox')) return <FirefoxLogo size={size} />;
  if (proc.includes('opera') || name.includes('opera')) return <AdobeLogo size={size} label="O" bg="#FF1B2D" textCol="#FFFFFF" />;
  if (proc.includes('vivaldi') || name.includes('vivaldi')) return <AdobeLogo size={size} label="V" bg="#EF3939" textCol="#FFFFFF" />;
  if (proc.includes('arc') || name.includes('arc browser')) return <AdobeLogo size={size} label="Arc" bg="#5433FF" textCol="#FFFFFF" />;
  
  // --- Development & Engineering ---
  if (proc.includes('code.exe') || id === 'vscode' || name.includes('visual studio code')) return <VsCodeLogo size={size} />;
  if (proc.includes('devenv') || name.includes('visual studio 20') || name.includes('visual studio ide')) return <VisualStudioLogo size={size} />;
  if (proc.includes('pycharm') || name.includes('pycharm')) return <AdobeLogo size={size} label="PC" bg="#21D789" textCol="#000000" />;
  if (proc.includes('idea') || name.includes('intellij')) return <AdobeLogo size={size} label="IJ" bg="#FE315D" textCol="#FFFFFF" />;
  if (proc.includes('clion') || name.includes('clion')) return <AdobeLogo size={size} label="CL" bg="#00CDD7" textCol="#000000" />;
  if (proc.includes('webstorm') || name.includes('webstorm')) return <AdobeLogo size={size} label="WS" bg="#00CDD7" textCol="#000000" />;
  if (proc.includes('rider') || name.includes('rider')) return <AdobeLogo size={size} label="RD" bg="#C70066" textCol="#FFFFFF" />;
  if (proc.includes('studio64') || name.includes('android studio')) return <AdobeLogo size={size} label="AS" bg="#3DDC84" textCol="#073042" />;
  if (proc.includes('git') || name.includes('git ') || name === 'git' || id.includes('git')) return <GitLogo size={size} />;
  if (proc.includes('docker') || name.includes('docker') || id.includes('docker')) return <DockerLogo size={size} />;
  if (proc.includes('python') || id.includes('python') || id.includes('orbit_gateway') || name.includes('python') || name.includes('orbit python')) return <PythonLogo size={size} />;
  if (proc.includes('ollama') || name.includes('ollama') || id.includes('ollama')) return <OllamaLogo size={size} />;
  if (proc.includes('postman') || name.includes('postman')) return <PostmanLogo size={size} />;
  if (proc.includes('blender') || name.includes('blender')) return <BlenderLogo size={size} />;

  // --- Communication & Productivity ---
  if (proc.includes('discord') || name.includes('discord') || id.includes('discord')) return <DiscordLogo size={size} />;
  if (proc.includes('slack') || name.includes('slack') || id.includes('slack')) return <SlackLogo size={size} />;
  if (proc.includes('teams') || name.includes('teams') || id.includes('teams')) return <TeamsLogo size={size} />;
  if (proc.includes('spotify') || name.includes('spotify') || id.includes('spotify')) return <SpotifyLogo size={size} />;
  if (proc.includes('zoom') || name.includes('zoom')) return <ZoomLogo size={size} />;
  if (proc.includes('telegram') || name.includes('telegram')) return <TelegramLogo size={size} />;
  if (proc.includes('whatsapp') || name.includes('whatsapp')) return <WhatsAppLogo size={size} />;
  if (proc.includes('steam') || name.includes('steam')) return <SteamLogo size={size} />;
  if (proc.includes('vlc') || name.includes('vlc')) return <VlcLogo size={size} />;
  if (proc.includes('notion') || name.includes('notion')) return <NotionLogo size={size} />;
  if (proc.includes('obsidian') || name.includes('obsidian')) return <ObsidianLogo size={size} />;

  // --- Microsoft Office ---
  if (proc.includes('winword') || name.includes('word') || id.includes('word')) return <WordLogo size={size} />;
  if (proc.includes('excel') || name.includes('excel') || id.includes('excel')) return <ExcelLogo size={size} />;
  if (proc.includes('powerpnt') || name.includes('powerpoint') || id.includes('powerpoint')) return <PowerPointLogo size={size} />;
  if (proc.includes('onenote') || name.includes('onenote') || id.includes('onenote')) return <OneNoteLogo size={size} />;
  if (proc.includes('outlook') || name.includes('outlook') || id.includes('outlook')) return <OutlookLogo size={size} />;

  // --- Adobe ---
  if (proc.includes('photoshop') || name.includes('photoshop')) return <AdobeLogo size={size} label="Ps" bg="#001E36" textCol="#31A8FF" />;
  if (proc.includes('illustrator') || name.includes('illustrator')) return <AdobeLogo size={size} label="Ai" bg="#330000" textCol="#FF9A00" />;
  if (proc.includes('premiere') || name.includes('premiere')) return <AdobeLogo size={size} label="Pr" bg="#00005B" textCol="#9999FF" />;
  if (proc.includes('acrobat') || name.includes('acrobat') || name.includes('reader')) return <AdobeLogo size={size} label="Ac" bg="#FF0000" textCol="#FFFFFF" />;

  // --- Windows Core Tools ---
  if (proc.includes('explorer') || name.includes('file explorer') || id.includes('explorer')) return <FileExplorerLogo size={size} />;
  if (proc.includes('taskmgr') || name.includes('task manager') || id.includes('taskmgr')) return <TaskManagerLogo size={size} />;
  if (proc.includes('systemsettings') || name.includes('settings') || id === 'control' || name.includes('control panel')) return <WindowsSettingsLogo size={size} />;
  if (proc.includes('wt.exe') || name.includes('windows terminal') || id === 'terminal') return <WindowsTerminalLogo size={size} />;
  if (proc.includes('powershell') || name.includes('powershell') || id.includes('powershell')) return <PowerShellLogo size={size} />;
  if (proc.includes('cmd.exe') || name.includes('command prompt') || id === 'cmd') return <CommandPromptLogo size={size} />;
  if (proc.includes('regedit') || name.includes('registry') || id.includes('regedit')) return <RegistryEditorLogo size={size} />;
  if (proc.includes('notepad') || name.includes('notepad')) return <NotepadLogo size={size} />;
  if (proc.includes('mspaint') || name.includes('paint')) return <PaintLogo size={size} />;
  if (proc.includes('calc') || name.includes('calculator')) return <CalculatorLogo size={size} />;
  if (proc.includes('snippingtool') || name.includes('snipping')) return <SnippingToolLogo size={size} />;
  if (proc.includes('services.msc') || name.includes('services')) return <WindowsSettingsLogo size={size} />;
  if (proc.includes('devmgmt') || name.includes('device manager')) return <TaskManagerLogo size={size} />;

  // Tier 2: Extracted Native Windows Icon Data URL (from Electron app.getFileIcon)
  if (app?.iconDataUrl && !imgError) {
    return (
      <img
        src={app.iconDataUrl}
        alt={app.name || 'App'}
        width={size}
        height={size}
        style={{
          width: size,
          height: size,
          objectFit: 'contain',
          display: 'block',
          imageRendering: 'auto',
        }}
        onError={() => setImgError(true)}
        className={className}
      />
    );
  }

  // Tier 3: Category Fallback Badges
  if (cat.includes('browser') || app?.iconType === 'browser') {
    return <GlobeWebIcon size={size * 0.75} color="var(--accent-primary)" />;
  }
  if (cat.includes('development') || cat.includes('code') || app?.iconType === 'code' || app?.iconType === 'terminal') {
    return <TerminalIcon size={size * 0.75} color="var(--accent-primary)" />;
  }
  if (cat.includes('ai') || app?.iconType === 'ai') {
    return <ServerIcon size={size * 0.75} color="var(--accent-primary)" />;
  }
  if (cat.includes('system') || app?.iconType === 'system') {
    return <CpuChipIcon size={size * 0.75} color="var(--text-secondary)" />;
  }
  if (cat.includes('security')) {
    return <ShieldIcon size={size * 0.75} color="var(--accent-primary)" />;
  }

  return <AppsTabIcon size={size * 0.75} color="var(--text-muted)" />;
};
