// React Bits components are plain JSX with no types. Declare just enough for the ones we use.
declare module "@/components/SwipeToast" {
  import type { ReactNode } from "react";
  export interface SwipeToastProps {
    title?: string;
    description?: string;
    icon?: ReactNode;
    actionLabel?: string;
    onAction?: () => void;
    open?: boolean;
    onClose?: (reason: string) => void;
    background?: string;
    color?: string;
    fuseColor?: string;
    width?: number;
    radius?: number;
    slideMs?: number;
    settleBounce?: number;
    swipeDistance?: number;
    duration?: number;
    fuse?: "top" | "bottom";
    pauseOnHover?: boolean;
    closeButton?: boolean;
    inline?: boolean;
    dismissible?: boolean;
    className?: string;
  }
  export default function SwipeToast(props: SwipeToastProps): JSX.Element;
}

declare module "@/components/Antigravity" {
  const Antigravity: (props: Record<string, unknown>) => JSX.Element;
  export default Antigravity;
}

declare module "@/components/TechText" {
  const TechText: (props: Record<string, unknown>) => JSX.Element;
  export default TechText;
}
