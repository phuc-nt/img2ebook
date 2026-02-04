import React, { useState, useEffect } from 'react';

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [driveUrl, setDriveUrl] = useState('');
  const [status, setStatus] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [downloadLink, setDownloadLink] = useState('');

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('status') === 'success') {
      setIsLoggedIn(true);
      setStatus('Successfully connected to Google Drive!');
      // Cleanup URL
      window.history.replaceState({}, document.title, "/");
    }

    fetch('http://localhost:8000/api/user')
      .then(res => res.json())
      .then(data => {
        if (data.logged_in) setIsLoggedIn(true);
      })
      .catch(err => console.error("Server not reachable yet"));
  }, []);

  const handleConnect = async () => {
    try {
      const response = await fetch('http://localhost:8000/auth/login');
      const data = await response.json();
      window.location.href = data.url;
    } catch (err) {
      alert('Error connecting to backend. Make sure the server is running on port 8000.');
    }
  };

  const handleLogout = async () => {
    try {
      await fetch('http://localhost:8000/auth/logout');
      setIsLoggedIn(false);
      setDownloadLink('');
      setDriveUrl('');
      setStatus('');
    } catch (err) {
      console.error("Logout failed");
    }
  };

  const handleCancel = async () => {
    try {
      await fetch('http://localhost:8000/api/cancel', { method: 'POST' });
      setStatus('Cancelling...');
    } catch (err) {
      console.error("Cancel failed");
    }
  };

  const [progress, setProgress] = useState({ percent: 0, message: '' });
  const [mode, setMode] = useState('pdf'); // 'pdf' or 'ocr'
  const [apiKey, setApiKey] = useState(localStorage.getItem('gemini_apiKey') || '');

  const handleConvert = async () => {
    if (!driveUrl) {
      alert('Please paste a Google Drive folder link');
      return;
    }

    // Save API key
    if (apiKey) localStorage.setItem('gemini_apiKey', apiKey);

    if (mode === 'ocr' && !apiKey) {
      alert('Gemini API Key is required for Smart OCR mode');
      return;
    }

    setIsLoading(true);
    setProgress({ percent: 0, message: 'Starting...' });
    setDownloadLink('');
    setStatus('');

    // Start listening to progress stream
    const eventSource = new EventSource('http://localhost:8000/api/progress');
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setProgress({ percent: data.percent, message: data.message });
      if (data.status === 'complete' || data.status === 'error') {
        eventSource.close();
      }
    };

    try {
      const endpoint = mode === 'pdf' ? 'http://localhost:8000/api/convert' : 'http://localhost:8000/api/ocr/convert';
      const body = { url: driveUrl };
      if (mode === 'ocr') body.api_key = apiKey;

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(600000) // 10 minutes for OCR
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      if (data.success) {
        setStatus('Conversion successful!');
        setDownloadLink('http://localhost:8000/api/download');
      } else {
        setStatus('Error: ' + data.error);
        setProgress({ percent: 0, message: 'Failed' });
      }
    } catch (err) {
      console.error("Fetch Error:", err);
      setStatus('Error: ' + (err.message || "Failed to connect to server"));
      setProgress({ percent: 0, message: 'Connection Error' });
    } finally {
      setIsLoading(false);
      eventSource.close();
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4">
      {/* Abstract Background Decoration */}
      <div className="absolute top-1/4 -left-20 w-72 h-72 bg-blue-600/20 rounded-full blur-[120px]"></div>
      <div className="absolute bottom-1/4 -right-20 w-72 h-72 bg-indigo-600/20 rounded-full blur-[120px]"></div>

      <div className="relative max-w-md w-full bg-slate-900/50 backdrop-blur-xl border border-slate-800 rounded-3xl shadow-2xl p-8 space-y-8">
        <div className="text-center">
          <div className="inline-block p-3 bg-blue-500/10 rounded-2xl mb-4">
            <svg className="w-8 h-8 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">
            Drive to Ebook
          </h1>
          <p className="text-slate-400 mt-2 text-sm">Transform images into elegant PDF books</p>
        </div>

        {!isLoggedIn ? (
          <div className="space-y-6">
            <p className="text-slate-400 text-center text-sm px-4">
              Connect your Google Drive to pick folders and process images securely.
            </p>
            <button
              onClick={handleConnect}
              className="w-full flex items-center justify-center gap-3 bg-white text-slate-950 font-bold py-4 px-6 rounded-2xl hover:bg-slate-200 transition-all transform hover:scale-[1.02] active:scale-[0.98] shadow-xl"
            >
              <img src="https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png" className="w-6 h-6" alt="Google" />
              Sign in with Google
            </button>
          </div>
        ) : (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="flex flex-col items-center gap-4">
              <div className="flex items-center justify-center gap-2 py-2 px-4 bg-emerald-500/10 border border-emerald-500/20 rounded-full w-fit">
                <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span>
                <span className="text-emerald-400 text-xs font-semibold uppercase tracking-wider">Drive Connected</span>
              </div>
              <button
                onClick={handleLogout}
                className="text-[10px] text-slate-500 hover:text-slate-300 uppercase tracking-widest transition-colors"
              >
                Sign out / Switch Account
              </button>
            </div>

            <div className="flex justify-center gap-4 mb-6">
              <button
                onClick={() => setMode('pdf')}
                className={`flex-1 py-3 rounded-xl font-bold text-sm transition-all border ${mode === 'pdf' ? 'bg-blue-600 border-blue-500 text-white shadow-lg' : 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700'}`}
              >
                📕 PDF Ebook
              </button>
              <button
                onClick={() => setMode('ocr')}
                className={`flex-1 py-3 rounded-xl font-bold text-sm transition-all border ${mode === 'ocr' ? 'bg-purple-600 border-purple-500 text-white shadow-lg' : 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700'}`}
              >
                ✨ Smart OCR
              </button>
            </div>

            <div className={`space-y-4 transition-opacity duration-300 ${isLoading ? 'opacity-50 pointer-events-none' : ''}`}>
              <div className="space-y-2">
                <label className="text-xs font-bold text-slate-500 uppercase tracking-widest ml-1">Google Drive Link</label>
                <input
                  type="text"
                  value={driveUrl}
                  disabled={isLoading}
                  onChange={(e) => setDriveUrl(e.target.value)}
                  placeholder="Paste folder link here..."
                  className="w-full bg-slate-800/50 border border-slate-700 rounded-2xl py-4 px-5 text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all shadow-inner disabled:cursor-not-allowed"
                />
              </div>

              {mode === 'ocr' && (
                <div className="space-y-2 animate-in fade-in slide-in-from-top-2">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-widest ml-1">Gemini API Key</label>
                  <input
                    type="password"
                    value={apiKey}
                    disabled={isLoading}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="AI Studio API Key..."
                    className="w-full bg-slate-800/50 border border-slate-700 rounded-2xl py-4 px-5 text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition-all shadow-inner disabled:cursor-not-allowed"
                  />
                  <p className="text-[10px] text-slate-500 px-2">Get key at <a href="https://aistudio.google.com/" target="_blank" className="text-purple-400 hover:underline">aistudio.google.com</a></p>
                </div>
              )}
            </div>

            {isLoading && (
              <div className="space-y-4 animate-in fade-in duration-300">
                <div className="space-y-2">
                  <div className="flex justify-between text-xs text-blue-400 font-medium px-1">
                    <span className="truncate max-w-[70%]">{progress.message}</span>
                    <span>{progress.percent}%</span>
                  </div>
                  <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-300 ease-out"
                      style={{ width: `${progress.percent}%` }}
                    ></div>
                  </div>
                </div>

                <button
                  onClick={handleCancel}
                  className="w-full py-3 px-4 rounded-xl border border-red-500/30 text-red-400 hover:bg-red-500/10 font-semibold text-sm transition-all"
                >
                  Stop Processing
                </button>
              </div>
            )}

            {!downloadLink && !isLoading && (
              <button
                onClick={handleConvert}
                disabled={!driveUrl}
                className={`w-full bg-gradient-to-r ${mode === 'ocr' ? 'from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500' : 'from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500'} text-white font-bold py-4 px-6 rounded-2xl shadow-xl shadow-blue-500/20 transition-all transform hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none`}
              >
                {mode === 'ocr' ? 'Start AI Analysis' : 'Create Ebook Now'}
              </button>
            )}

            {downloadLink && (
              <a
                href={downloadLink}
                download
                className="w-full flex items-center justify-center gap-2 bg-slate-800 hover:bg-slate-700 text-blue-400 font-bold py-4 px-6 rounded-2xl border border-blue-500/30 transition-all"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download PDF Ebook
              </a>
            )}
          </div>
        )}

        {status && !downloadLink && (
          <p className="text-center text-xs text-slate-500 font-medium">
            {status}
          </p>
        )}
      </div>

      <p className="mt-8 text-slate-700 text-[10px] font-bold uppercase tracking-[0.2em]">
        Developed with Antigravity
      </p>
    </div>
  );
}

export default App;
