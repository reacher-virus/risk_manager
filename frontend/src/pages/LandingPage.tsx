import {
  Activity,
  ArrowRight,
  BarChart3,
  Database,
  FileText,
  Gauge,
  KeyRound,
  Lock,
  Mail,
  Network,
  ShieldCheck,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { ScrollLink } from "@/components/ScrollLink";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { NetworkHero3D } from "@/components/ui/network-hero-3d";
import { SITE } from "@/lib/site";

const STATS = [
  { value: "87.5%", label: "lower expected loss than a rules-only baseline" },
  { value: "94%", label: "of fraud caught (recall)" },
  { value: "0.85", label: "PR-AUC on unseen, later-in-time data" },
];

const STEPS = [
  {
    n: "01",
    title: "Bring your transactions",
    text: "Send them to the API, upload a CSV, or fire a realistic fraud scenario from the simulator to see the system react.",
  },
  {
    n: "02",
    title: "Score and explain",
    text: "Behaviour features, a calibrated model and a linked-account graph give every transaction a risk score and the reasons behind it.",
  },
  {
    n: "03",
    title: "Decide and learn",
    text: "Pick the operating point by what mistakes cost you. Analysts review alerts, and their verdicts feed the next retrain.",
  },
];

const SECURITY = [
  {
    icon: Lock,
    title: "Two-step sign-in",
    text: "Password plus a one-time code emailed to you. A stolen password alone is not enough.",
  },
  {
    icon: KeyRound,
    title: "Sessions you can trust",
    text: "HttpOnly cookies page scripts cannot read, CSRF protection, instant revocation on every device.",
  },
  {
    icon: Gauge,
    title: "Brute-force resistant",
    text: "CAPTCHA, per-account lockout and per-IP limits on every entry point, stored in the database.",
  },
  {
    icon: ShieldCheck,
    title: "HTTPS everywhere",
    text: "Automatic redirect, HSTS and Secure cookies in production. The server refuses to start unsafely.",
  },
  {
    icon: Users,
    title: "Role-based access",
    text: "Viewer, analyst and admin, enforced on the server for every request, not just hidden in the UI.",
  },
  {
    icon: FileText,
    title: "Full audit trail",
    text: "Every score, review, sign-in and setting change is recorded and reviewable by admins.",
  },
];

const FAQ = [
  {
    q: "Is the data real?",
    a: "No. The demo runs on a synthetic transaction dataset so that every feature (devices, shared cards, fraud rings) can be shown honestly. The metrics on this page describe that simulation, not your business. Point the pipeline at your own data to get real numbers.",
  },
  {
    q: "Will it block payments by itself?",
    a: "No. It recommends one of four actions (allow, monitor, review, hold for verification). People stay in the loop, and nothing moves money automatically.",
  },
  {
    q: "How does it avoid bothering good customers?",
    a: "You tell it what a false alarm costs versus a missed fraud. The threshold is chosen to minimise your expected loss, and a live slider shows precisely what changes when you move it.",
  },
  {
    q: "Why can I trust the accuracy numbers?",
    a: "Evaluation uses a held-out test period that is later in time than the training data, outcomes only reach the features after a realistic delay, and the test set is evaluated once. Results are reported even when they miss the targets.",
  },
  {
    q: "How do I get access?",
    a: "Create an account, confirm your email with the code we send, then sign in. New accounts start as viewers; an administrator can grant analyst access.",
  },
];

function ShapMini() {
  const rows: [string, number, boolean][] = [
    ["Accounts on this device (24h)", 92, true],
    ["Account is 0 days old", 64, true],
    ["Amount vs. customer average", 38, true],
    ["Customer prior history", 26, false],
  ];
  return (
    <div className="mini-shap" aria-hidden="true">
      {rows.map(([label, w, up]) => (
        <div key={label} className="mini-shap__row">
          <span>{label}</span>
          <i className={up ? "up" : "down"} style={{ width: `${w}%` }} />
        </div>
      ))}
    </div>
  );
}

function CostMini() {
  return (
    <svg
      className="mini-cost"
      viewBox="0 0 200 80"
      role="img"
      aria-label="A cost curve with a clear lowest point"
    >
      <path
        d="M4 14 C 40 70, 70 74, 100 66 S 160 40, 196 18"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        opacity="0.5"
      />
      <circle cx="84" cy="69" r="5" fill="#f97316" />
      <path d="M84 8v54" stroke="#f97316" strokeDasharray="3 3" />
    </svg>
  );
}

function NetworkMini() {
  const pts: [number, number][] = [
    [100, 40],
    [40, 16],
    [160, 18],
    [30, 62],
    [170, 64],
    [100, 74],
    [64, 40],
    [138, 42],
  ];
  return (
    <svg
      className="mini-net"
      viewBox="0 0 200 90"
      role="img"
      aria-label="Several accounts linked to one shared device"
    >
      {pts.slice(1).map(([x, y]) => (
        <line
          key={`${x}${y}`}
          x1="100"
          y1="40"
          x2={x}
          y2={y}
          stroke="#f97316"
          strokeOpacity="0.6"
        />
      ))}
      {pts.map(([x, y], i) =>
        i === 0 ? (
          <rect
            key="d"
            x="93"
            y="33"
            width="14"
            height="14"
            rx="3"
            fill="#f97316"
          />
        ) : (
          <circle
            key={`${x}${y}`}
            cx={x}
            cy={y}
            r="5"
            fill="currentColor"
            opacity="0.8"
          />
        ),
      )}
    </svg>
  );
}

export function LandingPage() {
  return (
    <div className="site">
      <SiteHeader />
      <main>
        <section className="lp-hero" aria-labelledby="hero-title">
          <div className="lp-hero__text">
            <p className="lp-badge">
              <Activity size={14} aria-hidden="true" /> Defense-only ·
              Explainable · Cost-aware
            </p>
            <h1 id="hero-title" className="lp-hero__title">
              Stop fraud before it costs you.
              <br />
              <span className="lp-gradient">Know exactly why.</span>
            </h1>
            <p className="lp-hero__lead">
              {SITE.name} scores every transaction, explains the decision in
              plain English, finds networks of linked accounts, and picks the
              cheapest safe action using your real costs.
            </p>
            <div className="btn-row lp-hero__cta">
              <a className="btn btn--primary btn--lg" href="#/signup">
                Create your account <ArrowRight size={16} aria-hidden="true" />
              </a>
              <a className="btn btn--lg" href="#/signin">
                Sign in
              </a>
              <ScrollLink to="how" className="btn btn--ghost btn--lg">
                See how it works
              </ScrollLink>
            </div>
            <dl className="lp-stats">
              {STATS.map((s) => (
                <div key={s.value}>
                  <dt>
                    {s.value}
                    <sup>*</sup>
                  </dt>
                  <dd>{s.label}</dd>
                </div>
              ))}
            </dl>
            <p className="note">
              * Held-out test on synthetic data. Your results will differ.
            </p>
          </div>
          <div className="lp-hero__art">
            <NetworkHero3D />
            <p className="lp-hero__hint">
              Drag to rotate. The orange cluster is a fraud ring sharing one
              device.
            </p>
          </div>
        </section>

        <section
          id="features"
          className="lp-section"
          aria-labelledby="features-title"
        >
          <h2 id="features-title" className="lp-h2">
            Everything an analyst needs, nothing they have to guess
          </h2>
          <div className="bento">
            <article className="bento__card bento__card--wide">
              <BarChart3 size={20} aria-hidden="true" />
              <h3>Every decision explained</h3>
              <p>
                Real per-transaction attributions (SHAP) turned into
                plain-English reasons, so nobody acts on a black box.
              </p>
              <ShapMini />
            </article>
            <article className="bento__card">
              <SlidersHorizontal size={20} aria-hidden="true" />
              <h3>Priced in rupees</h3>
              <p>
                Choose the threshold by the cost of false alarms versus missed
                fraud.
              </p>
              <CostMini />
            </article>
            <article className="bento__card">
              <Network size={20} aria-hidden="true" />
              <h3>Sees linked accounts</h3>
              <p>
                Rings that hide behind many devices and cards still show up as
                one network.
              </p>
              <NetworkMini />
            </article>
            <article className="bento__card bento__card--wide">
              <Users size={20} aria-hidden="true" />
              <h3>Built for the analyst loop</h3>
              <p>
                Review, hold or escalate; confirm fraud or mark legitimate.
                Those verdicts are folded into the next retrain.
              </p>
            </article>
            <article className="bento__card">
              <Gauge size={20} aria-hidden="true" />
              <h3>Honest probabilities</h3>
              <p>
                Calibrated, so a score of 0.3 really means about a 30% chance.
              </p>
            </article>
            <article className="bento__card">
              <Activity size={20} aria-hidden="true" />
              <h3>Watches for drift</h3>
              <p>
                Population-stability checks tell you when the model is going
                stale and when to retrain.
              </p>
            </article>
            <article className="bento__card">
              <Database size={20} aria-hidden="true" />
              <h3>Bring your own data</h3>
              <p>
                REST API, CSV upload or the built-in simulator. Batch scoring
                never touches live state.
              </p>
            </article>
          </div>
        </section>

        <section id="how" className="lp-section" aria-labelledby="how-title">
          <h2 id="how-title" className="lp-h2">
            From raw transactions to a defensible decision
          </h2>
          <ol className="steps">
            {STEPS.map((s) => (
              <li key={s.n} className="steps__item">
                <span className="steps__n">{s.n}</span>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section
          id="security"
          className="lp-section"
          aria-labelledby="security-title"
        >
          <h2 id="security-title" className="lp-h2">
            Security is part of the product
          </h2>
          <ul className="sec-grid">
            {SECURITY.map(({ icon: Icon, title, text }) => (
              <li key={title} className="sec-grid__item">
                <Icon size={20} aria-hidden="true" />
                <h3>{title}</h3>
                <p>{text}</p>
              </li>
            ))}
          </ul>
        </section>

        <section
          id="results"
          className="lp-section"
          aria-labelledby="results-title"
        >
          <h2 id="results-title" className="lp-h2">
            Measured against a plain rules baseline
          </h2>
          <div className="table-wrap lp-table">
            <table className="table table--stack">
              <caption className="sr-only">
                Rules baseline compared with the learned model on a held-out
                test set
              </caption>
              <thead>
                <tr>
                  <th scope="col">Held-out test set</th>
                  <th scope="col" className="num">
                    Rules only
                  </th>
                  <th scope="col" className="num">
                    {SITE.name} model
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Precision</th>
                  <td className="num mono" data-label="Rules only">
                    44.1%
                  </td>
                  <td className="num mono" data-label={`${SITE.name} model`}>
                    73.9%
                  </td>
                </tr>
                <tr>
                  <th scope="row">Recall</th>
                  <td className="num mono" data-label="Rules only">
                    42.2%
                  </td>
                  <td className="num mono" data-label={`${SITE.name} model`}>
                    94.4%
                  </td>
                </tr>
                <tr>
                  <th scope="row">PR-AUC</th>
                  <td className="num mono" data-label="Rules only">
                    0.277
                  </td>
                  <td className="num mono" data-label={`${SITE.name} model`}>
                    0.851
                  </td>
                </tr>
                <tr className="table__total">
                  <th scope="row">
                    Expected loss (₹150 false alarm, ₹2,500 missed fraud)
                  </th>
                  <td className="num mono" data-label="Rules only">
                    ₹3,24,600
                  </td>
                  <td className="num mono" data-label={`${SITE.name} model`}>
                    ₹40,650
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="note">
            Evaluated once on a later time period than training. Synthetic data:
            these figures show the system works, not what you will see in
            production.
          </p>
        </section>

        <section
          id="faq"
          className="lp-section lp-section--narrow"
          aria-labelledby="faq-title"
        >
          <h2 id="faq-title" className="lp-h2">
            Questions, answered
          </h2>
          <div className="faq">
            {FAQ.map((f) => (
              <details key={f.q} className="faq__item">
                <summary>{f.q}</summary>
                <p>{f.a}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="lp-cta" aria-labelledby="cta-title">
          <h2 id="cta-title">Ready to see it catch a fraud ring?</h2>
          <p>
            Create an account, confirm your email, and run the simulator in
            minutes.
          </p>
          <div className="btn-row lp-cta__row">
            <a className="btn btn--primary btn--lg" href="#/signup">
              Create your account <ArrowRight size={16} aria-hidden="true" />
            </a>
            <a
              className="btn btn--lg"
              href="https://mail.google.com/mail/?view=cm&fs=1&to=yashpree237915%40gmail.com&su=Hello%20from%20the%20Risk%20Manager%20site"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Mail size={16} aria-hidden="true" /> Email {SITE.owner}
            </a>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
