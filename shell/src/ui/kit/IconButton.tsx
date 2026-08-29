// SPDX-License-Identifier: Apache-2.0
import { Button, type ButtonProps } from "./Button";

export type IconButtonProps = Omit<ButtonProps, "size" | "children"> & {
  icon: React.ReactNode;
  "aria-label": string;
  size?: "default" | "sm";
};

export function IconButton({ icon, size = "default", ...props }: IconButtonProps) {
  return (
    <Button size={size === "sm" ? "sm" : "icon"} {...props}>
      {icon}
    </Button>
  );
}
