import "./ambient-background.css";

type AmbientBackgroundProps = {
  mode: "auth" | "app";
};

export function AmbientBackground({ mode }: AmbientBackgroundProps) {
  return <div aria-hidden="true" className={`ambient-background ambient-background--${mode}`} />;
}
