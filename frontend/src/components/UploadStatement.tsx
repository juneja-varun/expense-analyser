import { useEffect, useRef, useState } from "react";

import { listSupportedBanks, uploadStatement } from "../api/finance";
import type { SupportedBank, UploadResult } from "../api/finance";

interface Props {
  onImported: () => void;
}

export function UploadStatement({ onImported }: Props) {
  const [banks, setBanks] = useState<SupportedBank[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listSupportedBanks()
      .then(setBanks)
      .catch(() => setBanks([]));
  }, []);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const uploaded = await uploadStatement(file);
      setResult(uploaded);
      // A parse failure is still a completed upload — refresh either way so
      // the statement appears in the history with its error.
      onImported();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <section className="card">
      <h2>Upload a statement</h2>

      <div
        className={`dropzone${dragging ? " dropzone--active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void upload(file);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          id="statement-file"
          accept=".pdf,.csv,.xls,.xlsx,.txt"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
          }}
        />
        <label htmlFor="statement-file">
          {busy ? "Importing…" : "Choose a statement, or drop one here"}
        </label>
        <p className="dropzone__hint">
          PDF, CSV or XLS, exactly as your bank provides it. Nothing leaves this machine.
        </p>
      </div>

      {error && <p className="notice notice--error">{error}</p>}

      {result?.status === "failed" && (
        <p className="notice notice--error">
          <strong>Couldn’t read {result.original_filename}.</strong> {result.error_message}
        </p>
      )}

      {result?.status === "parsed" && (
        <p className="notice notice--ok">
          {result.was_entirely_duplicate ? (
            <>
              <strong>Already imported.</strong> All {result.duplicates} transactions in this
              statement were already here, so nothing changed.
            </>
          ) : (
            <>
              <strong>Imported {result.created} transactions</strong>
              {result.duplicates > 0 && ` (${result.duplicates} were already here)`} from{" "}
              {result.source_name ?? result.bank_slug}.
            </>
          )}
        </p>
      )}

      {banks.length > 0 && (
        <p className="muted small">
          Supported so far: {banks.map((b) => b.display_name).join(", ")}. Your bank missing?{" "}
          <a
            href="https://github.com/juneja-varun/expense-analyser/blob/main/docs/adding-a-bank-parser.md"
            target="_blank"
            rel="noreferrer"
          >
            Adding it is three files.
          </a>
        </p>
      )}
    </section>
  );
}
