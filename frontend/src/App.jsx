import { useState, useRef, useCallback } from 'react'

// ---------------------------------------------------------------------------
// Verdict styling
// ---------------------------------------------------------------------------

const VERDICT_STYLE = {
  COMPLIANT:    { bar: 'bg-green-500',  badge: 'bg-green-100 text-green-800 border-green-300'  },
  NONCOMPLIANT: { bar: 'bg-red-500',    badge: 'bg-red-100 text-red-800 border-red-300'        },
  UNVERIFIABLE: { bar: 'bg-amber-400',  badge: 'bg-amber-100 text-amber-800 border-amber-300'  },
  ERROR:        { bar: 'bg-gray-400',   badge: 'bg-gray-100 text-gray-700 border-gray-300'     },
}

const SEVERITY_BADGE = {
  error:   'bg-red-100 text-red-700',
  warning: 'bg-amber-100 text-amber-700',
}

// ---------------------------------------------------------------------------
// UploadZone — drag/drop + click-to-pick, thumbnail on selection
// ---------------------------------------------------------------------------

function UploadZone({ slot, label, required, onFile }) {
  const [file, setFile]       = useState(null)
  const [preview, setPreview] = useState(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  const accept = (f) => {
    setFile(f)
    setPreview(URL.createObjectURL(f))
    onFile(f)
  }

  const clear = (e) => {
    e.stopPropagation()
    setFile(null)
    if (preview) URL.revokeObjectURL(preview)
    setPreview(null)
    onFile(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const onDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) accept(f)
  }, [])

  const zone = file
    ? 'border-solid border-gray-200 bg-white cursor-default'
    : dragging
      ? 'border-solid border-blue-400 bg-blue-50 cursor-copy'
      : 'border-dashed border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50 cursor-pointer'

  return (
    <div
      onClick={() => !file && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`relative flex flex-col items-center justify-center rounded-xl border-2 p-4 transition-all h-60 w-full ${zone}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(e) => { const f = e.target.files[0]; if (f) accept(f) }}
      />

      {preview ? (
        <>
          <img
            src={preview}
            alt={`${slot} preview`}
            className="max-h-40 max-w-full object-contain rounded-lg shadow-sm"
          />
          <p className="mt-2 text-xs text-gray-500 truncate max-w-full px-2">{file.name}</p>
          <button
            onClick={clear}
            title="Remove"
            className="absolute top-2 right-2 rounded-full bg-white border border-gray-200 shadow-sm text-gray-500 hover:text-gray-800 w-6 h-6 flex items-center justify-center text-sm leading-none"
          >
            ×
          </button>
        </>
      ) : (
        <div className="text-center select-none">
          <div className="text-3xl text-gray-300 mb-2">↑</div>
          <p className="text-sm font-medium text-gray-600">
            {label}
            {required && <span className="text-red-400 ml-1">*</span>}
          </p>
          <p className="text-xs text-gray-400 mt-1">Drag & drop or click to browse</p>
          <p className="text-xs text-gray-400">JPEG · PNG · WebP · max 10 MB</p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ResultPanel — verdict, issues, metadata
// ---------------------------------------------------------------------------

function ResultPanel({ result }) {
  const sty = VERDICT_STYLE[result.verdict] ?? VERDICT_STYLE.ERROR

  return (
    <div className="mt-6 rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">

      {/* Colored verdict bar */}
      <div className={`h-1.5 w-full ${sty.bar}`} />

      {/* Verdict header */}
      <div className="flex flex-wrap items-center gap-2 px-5 py-4 border-b border-gray-100">
        <span className={`rounded-lg border px-3 py-1 text-lg font-bold tracking-wide ${sty.badge}`}>
          {result.verdict}
        </span>
        {result.partial_verification && (
          <span className="rounded-md bg-orange-100 border border-orange-200 px-2 py-0.5 text-xs font-medium text-orange-700">
            partial verification
          </span>
        )}
        {result.beverage_class && (
          <span className="ml-auto rounded-md bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
            {result.beverage_class}
          </span>
        )}
      </div>

      {/* Issues */}
      {result.issues?.length > 0 ? (
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">
            Issues ({result.issues.length})
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-400 border-b border-gray-100">
                  <th className="pb-2 pr-4 font-medium">Rule</th>
                  <th className="pb-2 pr-4 font-medium">Severity</th>
                  <th className="pb-2 pr-4 font-medium">Field</th>
                  <th className="pb-2 font-medium">Expected</th>
                </tr>
              </thead>
              <tbody>
                {result.issues.map((issue, i) => (
                  <tr key={i} className="border-b border-gray-50 last:border-0">
                    <td className="py-2 pr-4 font-mono text-gray-700 whitespace-nowrap">{issue.rule_id}</td>
                    <td className="py-2 pr-4">
                      <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${SEVERITY_BADGE[issue.severity] ?? SEVERITY_BADGE.warning}`}>
                        {issue.severity}
                      </span>
                    </td>
                    <td className="py-2 pr-4 font-mono text-gray-600 whitespace-nowrap">{issue.field}</td>
                    <td className="py-2 text-gray-600 text-xs leading-relaxed">{issue.expected}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="px-5 py-4 border-b border-gray-100 text-sm text-gray-400">
          No issues found.
        </div>
      )}

      {/* Metadata */}
      <div className="px-5 py-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-gray-400">
        <span><span className="font-medium text-gray-500">request_id </span>{result.request_id}</span>
        <span><span className="font-medium text-gray-500">model </span>{result.extraction_model}</span>
        {result.input_tokens != null && (
          <span><span className="font-medium text-gray-500">tokens </span>{result.input_tokens} in / {result.output_tokens} out</span>
        )}
        <span><span className="font-medium text-gray-500">schema_violations </span>{result.schema_violations ?? 0}</span>
        {result.front_label_ref && (
          <span className="col-span-2 font-mono break-all">
            <span className="font-medium not-italic text-gray-500">front </span>{result.front_label_ref}
          </span>
        )}
        {result.back_label_ref && (
          <span className="col-span-2 font-mono break-all">
            <span className="font-medium not-italic text-gray-500">back  </span>{result.back_label_ref}
          </span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [front,   setFront]   = useState(null)
  const [back,    setBack]    = useState(null)
  const [apiKey,  setApiKey]  = useState('')
  const [result,  setResult]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const handleSubmit = async () => {
    if (!front) return
    setLoading(true)
    setError(null)
    setResult(null)

    const formData = new FormData()
    formData.append('front', front)
    if (back) formData.append('back', back)

    const headers = {}
    if (apiKey.trim()) headers['X-API-Key'] = apiKey.trim()

    try {
      const res  = await fetch('/v1/check', { method: 'POST', headers, body: formData })
      const data = await res.json()
      if (!res.ok) {
        setError(`${res.status} ${res.statusText}: ${data.detail ?? JSON.stringify(data)}`)
      } else {
        setResult(data)
      }
    } catch (e) {
      setError(`Network error: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">

      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto flex items-baseline gap-3">
          <h1 className="text-lg font-semibold text-gray-900">TTB Label Compliance Checker</h1>
          <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 border border-amber-200">
            prototype
          </span>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8">

        {/* Upload panels */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Front panel <span className="text-red-400">*</span>
            </label>
            <UploadZone slot="front" label="Front panel" required onFile={setFront} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Back panel{' '}
              <span className="text-gray-400 font-normal text-xs">(optional — improves coverage)</span>
            </label>
            <UploadZone slot="back" label="Back panel" onFile={setBack} />
          </div>
        </div>

        {/* API key + submit */}
        <div className="mt-4 flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-500 mb-1">
              API key{' '}
              <span className="font-normal text-gray-400">(leave blank if API_KEY is not set)</span>
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              placeholder="X-API-Key value"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <button
            onClick={handleSubmit}
            disabled={!front || loading}
            className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 active:bg-blue-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            {loading ? 'Checking…' : 'Check label'}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="mt-6 rounded-xl border border-gray-200 bg-white shadow-sm p-6 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/3 mb-3" />
            <div className="h-3 bg-gray-100 rounded w-2/3 mb-2" />
            <div className="h-3 bg-gray-100 rounded w-1/2" />
          </div>
        )}

        {/* Result */}
        {!loading && result && <ResultPanel result={result} />}

        {/* Footer */}
        <p className="mt-10 text-xs text-gray-400 text-center">
          Prototype — not certified by TTB. Not a substitute for legal or regulatory counsel.
          Checks 27 CFR Parts 4, 5, 7, and 16 only.
        </p>

      </main>
    </div>
  )
}
