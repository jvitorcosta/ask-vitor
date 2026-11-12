// Client for POST /ask/stream: sends a question and yields the answer as it streams in.
//
// The API answers with Server-Sent Events (SSE): text frames separated by a blank line.
//   data: {"token": "Vitor "}        <- one piece of the answer (default "message" event)
//   event: done / data: {}           <- the answer is complete
//   event: error / data: {"detail"}  <- the model failed mid-answer
// The browser's EventSource only supports GET, so we read the stream from fetch() ourselves.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class AskError extends Error {}

type Frame = { event: string; data: { token?: string; detail?: string } };

function parseFrame(frame: string): Frame {
  let event = "message";
  let data = {};
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice("event: ".length);
    else if (line.startsWith("data: ")) data = JSON.parse(line.slice("data: ".length));
  }
  return { event, data };
}

function messageForStatus(status: number): string {
  if (status === 422) return "Please type a question (up to 500 characters).";
  if (status === 503) return "The model is unavailable right now. Is Ollama running?";
  return `The API returned an unexpected error (${status}).`;
}

export async function* askStream(question: string, signal?: AbortSignal): AsyncGenerator<string> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error; // the user pressed Stop: not an error to show
    throw new AskError(`Could not reach the API at ${API_URL}. Is it running?`);
  }

  if (!response.ok || !response.body) throw new AskError(messageForStatus(response.status));

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    // A network chunk can end in the middle of a frame: keep the unfinished tail for next time.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const { event, data } = parseFrame(frame);
      if (event === "done") return;
      if (event === "error") throw new AskError("The model stopped in the middle of the answer.");
      if (data.token) yield data.token;
    }
  }
  throw new AskError("The connection closed before the answer finished.");
}
