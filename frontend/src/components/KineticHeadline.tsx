import type { CSSProperties } from 'react'

/** Splits a headline into per-word spans so it can rise in sequence. */
export function KineticHeadline({ text, className = '' }: { text: string; className?: string }) {
  return (
    <h1 className={`kinetic ${className}`}>
      {text.split(' ').map((word, i) => (
        <span className="word" key={`${word}-${i}`} style={{ '--i': i } as CSSProperties}>
          {word}
        </span>
      ))}
    </h1>
  )
}
