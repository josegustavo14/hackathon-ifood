import React from 'react'

const paths = {
  chef: <><path d="M7 15a5 5 0 0 1-2-9 5 5 0 0 1 8-2 5 5 0 0 1 6 8l-1 1v7H7z"/><path d="M7 16h11M10 9v3m5-3v3"/></>,
  book: <><path d="M4 4h6l2 2 2-2h6v15h-6l-2 2-2-2H4zM12 6v15"/></>,
  chat: <path d="M21 11a8 8 0 0 1-8 8H7l-5 3 2-7a8 8 0 1 1 17-4Z"/>,
  file: <><path d="M14 2H5v20h14V7zM14 2v6h5M8 13h8m-8 4h6"/></>,
  bag: <><path d="M4 7h16l1 14H3zM8 8V6a4 4 0 0 1 8 0v2"/></>,
  search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  check: <path d="m5 12 4 4L20 5"/>,
  leaf: <><path d="M20 3C6 1 1 8 6 16s17 0 14-13ZM4 21 16 8"/></>,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/></>,
  spark: <><path d="m12 3 3 6 6 3-6 3-3 6-3-6-6-3 6-3z"/></>,
  close: <path d="m6 6 12 12M6 18 18 6"/>,
}
export default function Icon({ name, size = 20, ...props }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.spark}</svg>
}
