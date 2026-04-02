import { useState } from "react";
import {
  runAllTests,
  testUtrExtraction,
  type TestResult,
} from "../api/endpoints";

const SAMPLE_SMS_TEXTS = [
  "Rs.499.00 credited to A/c XX1234 by UPI. UTR: 412345678901. Sender: user@upi",
  "Dear Customer, INR 299 has been received via UPI Ref No 987654321012 on 15-Jan-2025",
  "NEFT credit of Rs 1,999.00 Ref HDFC0001234567890 received in your account",
  "You have received Rs.149 via UPI. Transaction ID: 445566778899112233",
];

export default function TestPanel() {
  const [results, setResults] = useState<TestResult[]>([]);
  const [running, setRunning] = useState(false);
  const [smsText, setSmsText] = useState(SAMPLE_SMS_TEXTS[0]);
  const [utrResult, setUtrResult] = useState<TestResult | null>(null);
  const [testingUtr, setTestingUtr] = useState(false);

  const handleRunAll = async () => {
    setRunning(true);
    setResults([]);
    try {
      const res = await runAllTests();
      setResults(res);
    } catch (e) {
      setResults([
        {
          name: "Run All",
          success: false,
          message: `Failed to reach backend: ${e instanceof Error ? e.message : "Unknown error"}`,
          details: null,
          duration_ms: null,
        },
      ]);
    }
    setRunning(false);
  };

  const handleTestUtr = async () => {
    setTestingUtr(true);
    setUtrResult(null);
    try {
      const res = await testUtrExtraction(smsText);
      setUtrResult(res);
    } catch (e) {
      setUtrResult({
        name: "UTR Extraction",
        success: false,
        message: `Failed: ${e instanceof Error ? e.message : "Unknown error"}`,
        details: null,
        duration_ms: null,
      });
    }
    setTestingUtr(false);
  };

  const statusIcon = (success: boolean) => (success ? "✅" : "❌");
  const statusColor = (success: boolean) => (success ? "#d4edda" : "#f8d7da");
  const statusBorder = (success: boolean) => (success ? "#c3e6cb" : "#f5c6cb");

  return (
    <>
      <h1>🧪 Test Panel</h1>
      <p style={{ color: "#666", marginBottom: 20 }}>
        Run diagnostics to verify all platform components are working correctly.
      </p>

      {/* ── Run All Tests ─────────────────────────────── */}
      <div style={{ marginBottom: 32 }}>
        <button
          onClick={handleRunAll}
          disabled={running}
          style={{
            padding: "12px 32px",
            background: running ? "#95a5a6" : "#3498db",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            cursor: running ? "default" : "pointer",
            fontSize: 16,
            fontWeight: 600,
          }}
        >
          {running ? "⏳ Running Tests..." : "🚀 Run All Tests"}
        </button>

        {results.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <h3 style={{ marginBottom: 12 }}>
              Results:{" "}
              {results.filter((r) => r.success).length}/{results.length} passed
            </h3>
            {results.map((r, i) => (
              <div
                key={i}
                style={{
                  padding: 14,
                  marginBottom: 8,
                  background: statusColor(r.success),
                  border: `1px solid ${statusBorder(r.success)}`,
                  borderRadius: 8,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong>
                    {statusIcon(r.success)} {r.name}
                  </strong>
                  {r.duration_ms != null && (
                    <span style={{ fontSize: 12, color: "#666" }}>
                      {r.duration_ms.toFixed(1)}ms
                    </span>
                  )}
                </div>
                <div style={{ marginTop: 6, fontSize: 14 }}>{r.message}</div>
                {r.details && Object.keys(r.details).length > 0 && (
                  <details style={{ marginTop: 8, fontSize: 13 }}>
                    <summary style={{ cursor: "pointer", color: "#555" }}>
                      Details
                    </summary>
                    <pre
                      style={{
                        background: "rgba(0,0,0,0.05)",
                        padding: 10,
                        borderRadius: 4,
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        marginTop: 6,
                        fontSize: 12,
                      }}
                    >
                      {JSON.stringify(r.details, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── UTR Extraction Tester ─────────────────────── */}
      <div
        style={{
          padding: 20,
          background: "#fff",
          border: "1px solid #ddd",
          borderRadius: 8,
        }}
      >
        <h2 style={{ marginTop: 0, borderBottom: "2px solid #9b59b6", paddingBottom: 8 }}>
          🔍 UTR Extraction Tester
        </h2>
        <p style={{ color: "#666", fontSize: 14 }}>
          Paste a sample bank SMS / transaction message to test if the UTR and amount can be extracted.
        </p>

        {/* Quick-fill buttons */}
        <div style={{ marginBottom: 10 }}>
          <span style={{ fontSize: 12, color: "#888", marginRight: 8 }}>Quick samples:</span>
          {SAMPLE_SMS_TEXTS.map((txt, i) => (
            <button
              key={i}
              onClick={() => setSmsText(txt)}
              style={{
                marginRight: 6,
                marginBottom: 4,
                padding: "4px 10px",
                fontSize: 12,
                border: "1px solid #ccc",
                borderRadius: 4,
                background: smsText === txt ? "#eee" : "#fff",
                cursor: "pointer",
              }}
            >
              Sample {i + 1}
            </button>
          ))}
        </div>

        <textarea
          value={smsText}
          onChange={(e) => setSmsText(e.target.value)}
          rows={4}
          style={{
            width: "100%",
            padding: 10,
            border: "1px solid #ccc",
            borderRadius: 4,
            fontFamily: "monospace",
            fontSize: 13,
            marginBottom: 10,
          }}
          placeholder="Paste bank SMS text here..."
        />

        <button
          onClick={handleTestUtr}
          disabled={testingUtr || !smsText.trim()}
          style={{
            padding: "8px 20px",
            background: testingUtr ? "#95a5a6" : "#9b59b6",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            cursor: testingUtr ? "default" : "pointer",
            fontWeight: 600,
          }}
        >
          {testingUtr ? "Testing..." : "🔍 Extract UTR"}
        </button>

        {utrResult && (
          <div
            style={{
              marginTop: 12,
              padding: 14,
              background: statusColor(utrResult.success),
              border: `1px solid ${statusBorder(utrResult.success)}`,
              borderRadius: 8,
            }}
          >
            <strong>{statusIcon(utrResult.success)} {utrResult.message}</strong>
            {utrResult.details && (
              <pre
                style={{
                  background: "rgba(0,0,0,0.05)",
                  padding: 10,
                  borderRadius: 4,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  marginTop: 8,
                  fontSize: 12,
                }}
              >
                {JSON.stringify(utrResult.details, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </>
  );
}
