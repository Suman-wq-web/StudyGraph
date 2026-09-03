"use client";

import { forwardRef, useState, type ComponentProps } from "react";
import { Input } from "@/components/ui/Input";
import { IconEye, IconEyeOff } from "@/components/ui/icons";

type PasswordInputProps = Omit<ComponentProps<typeof Input>, "type" | "trailing">;

/** `Input` with a show/hide toggle in its `trailing` slot -- built on the
 * shared primitive rather than a standalone component, so it inherits the
 * same label/error/focus styling as every other field in the app. */
export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  (props, ref) => {
    const [visible, setVisible] = useState(false);

    return (
      <Input
        ref={ref}
        type={visible ? "text" : "password"}
        trailing={
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            className="flex h-4 w-4 items-center justify-center text-content-muted transition-colors hover:text-content-primary focus-visible:text-content-primary focus:outline-none"
            aria-label={visible ? "Hide password" : "Show password"}
          >
            {visible ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
          </button>
        }
        {...props}
      />
    );
  }
);
PasswordInput.displayName = "PasswordInput";
