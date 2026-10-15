import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { SITE, mailto } from "@/lib/site";

/** Custom 404 for any unknown route. */
export function NotFoundPage({ signedIn }: { signedIn: boolean }) {
  return (
    <div className="site">
      <SiteHeader />
      <main className="notfound">
        <p className="notfound__code" aria-hidden="true">
          404
        </p>
        <h1 className="notfound__title">This page could not be found</h1>
        <p className="notfound__text">
          The link may be mistyped or the page may have moved. Nothing is wrong
          with your account.
        </p>
        <div className="btn-row notfound__actions">
          <a className="btn btn--primary" href={signedIn ? "#/hero" : "#/"}>
            {signedIn ? "Go to your workspace" : "Back to home"}
          </a>
          {!signedIn && (
            <a className="btn" href="#/signin">
              Sign in
            </a>
          )}
          <a
            className="btn btn--ghost"
            href={`https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(SITE.email)}&su=${encodeURIComponent("Broken link on Risk Manager")}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Report a broken link
          </a>
        </div>
        <p className="note">
          Or write to {SITE.owner} at{" "}
          <a
            href={`https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(SITE.email)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            {SITE.email}
          </a>
          .
        </p>
      </main>
      <SiteFooter />
    </div>
  );
}
