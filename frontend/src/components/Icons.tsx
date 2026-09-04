import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement>
const base = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

export const PlusIcon = (p: P) => <svg {...base} {...p}><path d="M12 5v14M5 12h14" /></svg>
export const ArrowIcon = (p: P) => <svg {...base} {...p}><path d="m9 18 6-6-6-6" /></svg>
export const UploadIcon = (p: P) => <svg {...base} {...p}><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" /><path d="M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" /></svg>
export const HomeIcon = (p: P) => <svg {...base} {...p}><path d="m3 11 9-8 9 8" /><path d="M5 10v10h14V10M9 20v-6h6v6" /></svg>
export const RoomIcon = (p: P) => <svg {...base} {...p}><path d="M4 20V5h16v15M4 12h16" /><path d="M8 8h.01M16 16h.01" /></svg>
export const SparkIcon = (p: P) => <svg {...base} {...p}><path d="m12 3 1.25 4.1L17 9l-3.75 1.9L12 15l-1.25-4.1L7 9l3.75-1.9L12 3Z" /><path d="m18.5 14 .7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3Z" /></svg>
export const BackIcon = (p: P) => <svg {...base} {...p}><path d="m15 18-6-6 6-6" /></svg>
export const MoreIcon = (p: P) => <svg {...base} {...p}><circle cx="5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none"/></svg>
export const TrashIcon = (p: P) => <svg {...base} {...p}><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13" /><path d="M10 11v5M14 11v5" /></svg>
export const ImageIcon = (p: P) => <svg {...base} {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m21 15-5-5L5 20" /></svg>
export const LogOutIcon = (p: P) => <svg {...base} {...p}><path d="M10 5H5v14h5M14 8l4 4-4 4M18 12H9" /></svg>
export const IdeaIcon = (p: P) => <svg {...base} {...p}><path d="M9 18h6M10 22h4"/><path d="M8.3 14.5A6 6 0 1 1 15.7 14.5c-.9.8-1.5 1.7-1.7 2.5h-4c-.2-.8-.8-1.7-1.7-2.5Z"/></svg>
export const HistoryIcon = (p: P) => <svg {...base} {...p}><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></svg>
export const UserIcon = (p: P) => <svg {...base} {...p}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>
export const PlanIcon = (p: P) => <svg {...base} {...p}><path d="M4 4h16v16H4zM9 4v7h11M4 15h8v5M12 11v9"/></svg>
export const SiteIcon = (p: P) => <svg {...base} {...p}><path d="M4 19V5l5-2 6 3 5-2v14l-5 2-6-3-5 2Z"/><path d="M9 3v14M15 6v14"/></svg>
