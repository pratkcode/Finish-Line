import SiteHeader from "@/components/SiteHeader";

type Props = {
  title: string;
  description?: React.ReactNode;
  width?: "narrow" | "wide";
  children: React.ReactNode;
};

// Shared frame for app pages: header, title block, and content width.
export default function PageShell({ title, description, width = "wide", children }: Props) {
  return (
    <div className="flex flex-1 flex-col">
      <SiteHeader />
      <main
        className={`mx-auto w-full flex-1 px-4 pt-8 pb-16 sm:px-6 ${
          width === "narrow" ? "max-w-3xl" : "max-w-5xl"
        }`}
      >
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{title}</h1>
        {description && <p className="mt-1.5 mb-8 text-slate-600">{description}</p>}
        {!description && <div className="mb-8" />}
        {children}
      </main>
    </div>
  );
}
