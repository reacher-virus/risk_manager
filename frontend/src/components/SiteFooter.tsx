import { ScrollLink } from "@/components/ScrollLink";
import { Logo } from "@/components/Logo";
import { SECTIONS, SITE, copyrightYear } from "@/lib/site";

/** Every link here goes somewhere real: sections scroll, pages exist, mail and GitHub open in the right place. */
export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer__grid">
        <div className="site-footer__about">
          <div className="site-header__brand">
            <Logo size={36} />
            <a className="site-header__name" href="#/">
              {SITE.name}
            </a>
          </div>
          <p>
            {SITE.tagline}. A defense-only system for catching fraud, abusive
            returns and chargebacks.
          </p>
        </div>
        <nav aria-label="Product">
          <h2>Product</h2>
          {SECTIONS.map(([id, label]) => (
            <ScrollLink key={id} to={id}>
              {label}
            </ScrollLink>
          ))}
        </nav>
        <nav aria-label="Account">
          <h2>Account</h2>
          <a href="#/signin">Sign in</a>
          <a href="#/signup">Create account</a>
          <a href="#/admin-login">Administrator sign-in</a>
          <a href="#/forgot">Forgot password</a>
        </nav>
        <nav aria-label="Company">
          <h2>Legal &amp; contact</h2>
          <a href="#/privacy">Privacy Policy</a>
          <a href="#/terms">Terms of Service</a>
          <a
            href={`https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(SITE.email)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            {SITE.email}
          </a>
          <a href={SITE.github} target="_blank" rel="noopener noreferrer">
            Source code on GitHub
          </a>
        </nav>
      </div>
      <p className="site-footer__copy">
        © {copyrightYear()} {SITE.owner}. All rights reserved. Results shown are
        from synthetic data.
      </p>
    </footer>
  );
}
