import { Toaster as Sonner, type ToasterProps } from "sonner";

// shadcn/ui Sonner wrapper, themed with the Volt on Graphite palette (always dark).
export function Toaster(props: ToasterProps) {
  return (
    <Sonner
      theme="dark"
      position="top-center"
      toastOptions={{
        classNames: {
          toast: "!bg-surface-2 !border-line !text-ink !rounded-2xl",
          description: "!text-mute",
        },
      }}
      {...props}
    />
  );
}
