"use client"; // this page uses state and browser APIs (fetch streaming), so it runs in the browser

import { type FormEvent, useRef, useState } from "react";
import { AskError, askStream } from "@/lib/askStream";

type Status = "idle" | "streaming" | "done" | "error";

const EXAMPLES = ["Where has Vitor worked?", "What did the fraud model achieve?"];

export default function Home() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  async function ask(event: FormEvent) {
    event.preventDefault();
    const controller = new AbortController();
    abortRef.current = controller;
    setAnswer("");
    setError("");
    setStatus("streaming");

    try {
      for await (const token of askStream(question, controller.signal)) {
        setAnswer((previous) => previous + token); // append each piece as it arrives
      }
      setStatus("done");
    } catch (caught) {
      if (controller.signal.aborted) {
        setStatus("done"); // stopped by the user: keep the partial answer
        return;
      }
      setError(caught instanceof AskError ? caught.message : "Something went wrong.");
      setStatus("error");
    }
  }

  const streaming = status === "streaming";

  return (
    <main>
      <h1>Ask Vitor</h1>
      <p className="hint">Answers come from a local LLM, grounded only in Vitor&apos;s CV.</p>

      <form onSubmit={ask}>
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask something about Vitor…"
          maxLength={500}
          disabled={streaming}
          aria-label="Question"
        />
        {streaming ? (
          <button type="button" onClick={() => abortRef.current?.abort()}>
            Stop
          </button>
        ) : (
          <button type="submit" disabled={!question.trim()}>
            Ask
          </button>
        )}
      </form>

      <div className="examples">
        {EXAMPLES.map((example) => (
          <button key={example} type="button" onClick={() => setQuestion(example)} disabled={streaming}>
            {example}
          </button>
        ))}
      </div>

      {/* aria-live: screen readers announce the answer as it grows */}
      <section className="answer" aria-live="polite">
        {answer}
        {streaming && <span className="cursor">▍</span>}
      </section>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </main>
  );
}
