import { FormEvent, useState } from "react";
import * as api from "../api";

type AuthPageProps = { onAuthenticated: (response: api.AuthResponse) => void; sessionError?: string | null };

export function AuthPage({ onAuthenticated, sessionError }: AuthPageProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      const response = mode === "login"
        ? await api.login(username, password)
        : await api.register(username, email, password);
      onAuthenticated(response);
    } catch (err: unknown) {
      setError(api.errorMessage(err, "No se pudo completar la operación."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <div className="auth-brand">Diagramador UML</div>
        <p className="auth-kicker">Modelado visual colaborativo</p>
        <h1>{mode === "login" ? "Bienvenido de nuevo" : "Crea tu cuenta"}</h1>
        <p className="auth-copy">
          {mode === "login" ? "Inicia sesión para abrir tus diagramas." : "Regístrate para guardar y organizar tus diagramas."}
        </p>

        <div className="auth-tabs" role="tablist" aria-label="Autenticación">
          <button disabled={submitting} className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(null); }} type="button">Iniciar sesión</button>
          <button disabled={submitting} className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(null); }} type="button">Registrarse</button>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <label>Usuario<input value={username} onChange={(event) => setUsername(event.target.value)} required autoComplete="username" /></label>
          {mode === "register" && <label>Correo electrónico<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" /></label>}
          <label>Contraseña<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={mode === "register" ? 8 : undefined} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
          {(error || sessionError) && <div className="auth-error">{error || sessionError}</div>}
          <button className="auth-submit" disabled={submitting} type="submit">{submitting ? "Procesando..." : mode === "login" ? "Iniciar sesión" : "Crear cuenta"}</button>
        </form>
      </section>
      <aside className="auth-art">
        <span>Flujo de desarrollo</span>
        <strong>Del modelo<br />al backend.</strong>
        <p>Modela la estructura de tu sistema y genera su backend Spring Boot.</p>
        <ol className="auth-roadmap">
          <li>01 · Diagrama UML<small>Clases, atributos y relaciones.</small></li>
          <li>02 · Backend Spring Boot<small>Código, documentación y entrega del proyecto.</small></li>
          <li>03 · Aplicación móvil Flutter<small>Pendiente · Se conectará al backend generado.</small></li>
        </ol>
      </aside>
    </main>
  );
}
