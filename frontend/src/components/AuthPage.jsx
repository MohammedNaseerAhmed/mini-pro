/**
 * AuthPage — Sign In / Sign Up for LexAI
 * Simple, clean dark-luxury design. No role selection.
 */

import { useState } from "react";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

// ── Floating particle dots ─────────────────────────────────────────────────────
function Particles() {
  const dots = [
    { w:2, l:"12%", t:"18%", gold:true,  dur:5 },
    { w:1, l:"85%", t:"9%",  gold:false, dur:7 },
    { w:3, l:"70%", t:"75%", gold:true,  dur:6 },
    { w:1, l:"30%", t:"60%", gold:false, dur:8 },
    { w:2, l:"55%", t:"30%", gold:true,  dur:5.5 },
    { w:1, l:"20%", t:"85%", gold:false, dur:9 },
    { w:2, l:"90%", t:"50%", gold:true,  dur:6.5 },
    { w:1, l:"45%", t:"92%", gold:false, dur:7.5 },
    { w:3, l:"5%",  t:"45%", gold:true,  dur:5 },
    { w:1, l:"78%", t:"22%", gold:false, dur:8 },
  ];
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
      {dots.map((d, i) => (
        <span key={i} className="absolute rounded-full" style={{
          width: `${d.w}px`, height: `${d.w}px`,
          left: d.l, top: d.t,
          background: d.gold ? "rgba(201,168,76,0.6)" : "rgba(255,255,255,0.14)",
          animation: `authFloat ${d.dur}s ease-in-out ${i * 0.4}s infinite alternate`,
        }} />
      ))}
    </div>
  );
}

// ── Gold spinner ──────────────────────────────────────────────────────────────
function Spinner() {
  return (
    <span className="inline-block w-4 h-4 border-2 rounded-full" style={{
      borderColor: "rgba(201,168,76,0.3)",
      borderTopColor: "#C9A84C",
      animation: "authSpin 0.7s linear infinite",
    }} />
  );
}

// ── Input field ───────────────────────────────────────────────────────────────
function Field({ id, label, type = "text", placeholder, value, onChange, icon, disabled }) {
  const [show, setShow] = useState(false);
  const isPassword = type === "password";
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="label-xs ml-0.5">{label}</label>
      <div className="relative">
        {icon && (
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-sm select-none"
            style={{ opacity: 0.45 }}>
            {icon}
          </span>
        )}
        <input
          id={id}
          type={isPassword && show ? "text" : type}
          placeholder={placeholder}
          value={value}
          onChange={onChange}
          disabled={disabled}
          className="gold-input"
          style={{ paddingLeft: icon ? "2.4rem" : "1rem", paddingRight: isPassword ? "2.8rem" : "1rem" }}
          autoComplete={isPassword ? "new-password" : "on"}
        />
        {isPassword && (
          <button type="button" tabIndex={-1}
            onClick={() => setShow(s => !s)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-sm transition-opacity"
            style={{ opacity: 0.4 }}>
            {show ? "🙈" : "👁️"}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Inline error/success banner ───────────────────────────────────────────────
function Alert({ type, msg }) {
  if (!msg) return null;
  const cfg = {
    error:   { bg: "rgba(239,68,68,0.10)",  border: "rgba(239,68,68,0.30)",  text: "#fca5a5", icon: "⚠" },
    success: { bg: "rgba(34,197,94,0.10)",  border: "rgba(34,197,94,0.30)",  text: "#86efac", icon: "✓" },
  }[type] || {};
  return (
    <div className="flex items-start gap-2.5 rounded-xl px-4 py-3 text-sm animate-fade-up"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, color: cfg.text }}>
      <span className="font-bold mt-0.5">{cfg.icon}</span>
      <span className="leading-relaxed">{msg}</span>
    </div>
  );
}

// ── Sign In ───────────────────────────────────────────────────────────────────
function SignInForm({ onSuccess, onSwitch }) {
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password) { setError("Please fill in all fields."); return; }
    setLoading(true); setError("");
    try {
      const res  = await fetch(`${API_BASE}/auth/login`, {
        method:      "POST",
        credentials: "include",
        headers:     { "Content-Type": "application/json" },
        body:        JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || data.error || `Error ${res.status}`);
      onSuccess(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form id="sign-in-form" onSubmit={submit} className="space-y-5" noValidate>
      <Alert type="error" msg={error} />

      <Field id="si-email"    label="Email address" type="email"    placeholder="you@example.com"
        value={email}    onChange={e => setEmail(e.target.value)}    icon="✉️" disabled={loading} />
      <Field id="si-password" label="Password"      type="password" placeholder="Enter your password"
        value={password} onChange={e => setPassword(e.target.value)} icon="🔒" disabled={loading} />

      <button type="submit" id="sign-in-submit" disabled={loading}
        className="btn btn-primary w-full gap-2.5 mt-1"
        style={{ padding: "0.75rem 1.5rem", fontSize: "0.875rem", opacity: loading ? 0.75 : 1 }}>
        {loading ? <><Spinner /> Signing in…</> : "Sign In to LexAI"}
      </button>

      <p className="text-center text-xs" style={{ color: "#64748b" }}>
        New to LexAI?{" "}
        <button type="button" id="go-signup" onClick={onSwitch}
          className="font-semibold transition-colors"
          style={{ color: "#C9A84C" }}>
          Create an account
        </button>
      </p>
    </form>
  );
}

// ── Sign Up ───────────────────────────────────────────────────────────────────
function SignUpForm({ onSuccess, onSwitch }) {
  const [name,     setName]     = useState("");
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [confirm,  setConfirm]  = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim() || !email.trim() || !password || !confirm) {
      setError("Please fill in all fields."); return;
    }
    if (password !== confirm) { setError("Passwords do not match."); return; }
    if (password.length < 6)  { setError("Password must be at least 6 characters."); return; }
    setLoading(true); setError("");
    try {
      const res  = await fetch(`${API_BASE}/auth/register`, {
        method:      "POST",
        credentials: "include",
        headers:     { "Content-Type": "application/json" },
        body:        JSON.stringify({ name: name.trim(), email: email.trim().toLowerCase(), password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || data.error || `Error ${res.status}`);
      onSuccess(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form id="sign-up-form" onSubmit={submit} className="space-y-4" noValidate>
      <Alert type="error" msg={error} />

      <Field id="su-name"     label="Full name"         type="text"     placeholder="Your full name"
        value={name}     onChange={e => setName(e.target.value)}     icon="👤" disabled={loading} />
      <Field id="su-email"    label="Email address"     type="email"    placeholder="you@example.com"
        value={email}    onChange={e => setEmail(e.target.value)}    icon="✉️" disabled={loading} />
      <Field id="su-password" label="Password"          type="password" placeholder="Min. 6 characters"
        value={password} onChange={e => setPassword(e.target.value)} icon="🔒" disabled={loading} />
      <Field id="su-confirm"  label="Confirm password"  type="password" placeholder="Re-enter password"
        value={confirm}  onChange={e => setConfirm(e.target.value)}  icon="🔑" disabled={loading} />

      <button type="submit" id="sign-up-submit" disabled={loading}
        className="btn btn-primary w-full gap-2.5 mt-1"
        style={{ padding: "0.75rem 1.5rem", fontSize: "0.875rem", opacity: loading ? 0.75 : 1 }}>
        {loading ? <><Spinner /> Creating account…</> : "Create Account"}
      </button>

      <p className="text-center text-xs" style={{ color: "#64748b" }}>
        Already have an account?{" "}
        <button type="button" id="go-signin" onClick={onSwitch}
          className="font-semibold transition-colors"
          style={{ color: "#C9A84C" }}>
          Sign in
        </button>
      </p>
    </form>
  );
}

// ── Main AuthPage ─────────────────────────────────────────────────────────────
export default function AuthPage({ onAuth }) {
  const [tab,     setTab]     = useState("signin");
  const [success, setSuccess] = useState("");

  const switchTab = (t) => { setTab(t); setSuccess(""); };

  const handleSuccess = (data) => {
    const user = data.user;
    setSuccess(`Welcome, ${user?.name || "Counsel"}!`);
    if (data.token) localStorage.setItem("lex_token", data.token);
    if (user)       localStorage.setItem("lex_user",  JSON.stringify(user));
    setTimeout(() => onAuth(user), 1000);
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 relative overflow-hidden"
      style={{ background: "#05080f" }}>

      {/* Ambient orbs */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        <div className="absolute rounded-full" style={{
          width: "560px", height: "560px", top: "-100px", left: "calc(50% - 500px)",
          background: "radial-gradient(circle, rgba(201,168,76,0.06) 0%, transparent 70%)",
        }} />
        <div className="absolute rounded-full" style={{
          width: "480px", height: "480px", bottom: "-120px", right: "calc(50% - 480px)",
          background: "radial-gradient(circle, rgba(20,60,130,0.10) 0%, transparent 70%)",
        }} />
      </div>
      <Particles />

      <div className="relative z-10 w-full max-w-md animate-fade-up">

        {/* Logo */}
        <div className="text-center mb-8 space-y-2">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl border mx-auto"
            style={{ background: "rgba(201,168,76,0.10)", borderColor: "rgba(201,168,76,0.30)",
              boxShadow: "0 0 28px rgba(201,168,76,0.16)" }}>
            <span style={{ fontSize: "1.6rem" }}>⚖</span>
          </div>
          <div>
            <h1 className="legal-heading" style={{ fontSize: "2.25rem", letterSpacing: "-0.01em" }}>
              Lex<em className="text-gold-400" style={{ fontStyle: "italic" }}>AI</em>
            </h1>
            <p className="label-xs mt-1">AI-Powered Legal Intelligence</p>
          </div>
        </div>

        {/* Card */}
        <div className="glass-card overflow-hidden">

          {/* Tabs */}
          <div className="flex" style={{ borderBottom: "1px solid rgba(201,168,76,0.12)" }}>
            {[
              { id: "signin", label: "Sign In" },
              { id: "signup", label: "Sign Up" },
            ].map(t => (
              <button key={t.id} id={`tab-${t.id}`} type="button"
                onClick={() => switchTab(t.id)}
                className="flex-1 py-4 text-sm font-bold tracking-wider uppercase transition-all duration-200"
                style={{
                  color:        tab === t.id ? "#C9A84C" : "#64748b",
                  background:   tab === t.id ? "rgba(201,168,76,0.05)" : "transparent",
                  borderBottom: tab === t.id ? "2px solid #C9A84C" : "2px solid transparent",
                }}>
                {t.label}
              </button>
            ))}
          </div>

          {/* Body */}
          <div className="p-7">
            {success ? (
              <div className="py-10 flex flex-col items-center gap-3 animate-fade-up">
                <div className="w-14 h-14 rounded-full flex items-center justify-center text-2xl"
                  style={{ background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.3)" }}>
                  ✓
                </div>
                <p className="font-semibold text-lg" style={{ color: "#86efac" }}>{success}</p>
                <p className="text-sm" style={{ color: "#64748b" }}>Loading your workspace…</p>
              </div>
            ) : tab === "signin" ? (
              <SignInForm onSuccess={handleSuccess} onSwitch={() => switchTab("signup")} />
            ) : (
              <SignUpForm onSuccess={handleSuccess} onSwitch={() => switchTab("signin")} />
            )}
          </div>
        </div>

        <p className="text-center mt-5" style={{ fontSize: "11px", color: "#334155" }}>
          By continuing you agree to LexAI's{" "}
          <span className="cursor-pointer transition-colors" style={{ color: "rgba(201,168,76,0.55)" }}>Terms of Service</span>
          {" "}and{" "}
          <span className="cursor-pointer transition-colors" style={{ color: "rgba(201,168,76,0.55)" }}>Privacy Policy</span>.
        </p>
      </div>

      <style>{`
        @keyframes authSpin  { to { transform: rotate(360deg); } }
        @keyframes authFloat { from { transform: translateY(0px); } to { transform: translateY(-8px); } }
      `}</style>
    </div>
  );
}
