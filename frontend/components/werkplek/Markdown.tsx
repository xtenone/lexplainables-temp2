"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Rendert een agent-antwoord als (GitHub-flavored) Markdown. Geen rauwe HTML (geen rehype-raw), dus
 *  veilig; links laten we alleen door voor http(s) en openen extern. (Verhuisd uit ChatAssistent.) */
export function Markdown({ tekst }: { tekst: string }) {
  return (
    <div className="space-y-2 break-words text-sm text-ink [overflow-wrap:anywhere]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="leading-snug">{children}</p>,
          a: ({ href, children }) => {
            const veilig = typeof href === "string" && /^https?:\/\//i.test(href);
            return veilig ? (
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-lint underline underline-offset-2">
                {children}
              </a>
            ) : (
              <span>{children}</span>
            );
          },
          ul: ({ children }) => <ul className="ml-4 list-disc space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="ml-4 list-decimal space-y-0.5">{children}</ol>,
          h1: ({ children }) => <p className="text-sm font-semibold text-lint">{children}</p>,
          h2: ({ children }) => <p className="text-sm font-semibold text-lint">{children}</p>,
          h3: ({ children }) => <p className="font-semibold">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          code: ({ children }) => <code className="rounded bg-surface px-1 py-0.5 font-mono text-xs">{children}</code>,
          pre: ({ children }) => (
            <pre className="overflow-x-auto rounded border border-line bg-surface p-2 font-mono text-xs">{children}</pre>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border border-line px-2 py-1 text-left font-semibold">{children}</th>,
          td: ({ children }) => <td className="border border-line px-2 py-1 align-top">{children}</td>,
        }}
      >
        {tekst}
      </ReactMarkdown>
    </div>
  );
}
