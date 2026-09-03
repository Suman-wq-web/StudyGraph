import type { SVGProps } from "react";

/**
 * Hand-rolled outline icon set (24x24, stroke-based) so the app shell doesn't
 * need an icon package dependency. Every icon accepts standard SVG props --
 * size/color are controlled via `className` (e.g. `h-4 w-4 text-content-muted`).
 */

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {children}
    </svg>
  );
}

export function IconMenu(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3.75 6h16.5M3.75 12h16.5M3.75 18h16.5" />
    </Icon>
  );
}

export function IconClose(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 18 18 6M6 6l12 12" />
    </Icon>
  );
}

export function IconDashboard(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </Icon>
  );
}

export function IconLibrary(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H9a1.5 1.5 0 0 1 1.5 1.5v15A1.5 1.5 0 0 1 9 21H5.5A1.5 1.5 0 0 1 4 19.5v-15Z" />
      <path d="M13.5 4.5A1.5 1.5 0 0 1 15 3h3.5A1.5 1.5 0 0 1 20 4.5v15a1.5 1.5 0 0 1-1.5 1.5H15a1.5 1.5 0 0 1-1.5-1.5v-15Z" />
      <path d="M7 7h0M17 7h0" />
    </Icon>
  );
}

export function IconGraph(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="6" cy="6" r="2.25" />
      <circle cx="18" cy="6" r="2.25" />
      <circle cx="12" cy="18" r="2.25" />
      <path d="M7.9 7.3 10.3 16M16.1 7.3 13.7 16M8.25 6h7.5" />
    </Icon>
  );
}

export function IconChat(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v9a1.5 1.5 0 0 1-1.5 1.5H9l-4 3.5V16H5.5A1.5 1.5 0 0 1 4 14.5v-9Z" />
    </Icon>
  );
}

export function IconPath(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="5.5" cy="6" r="2" />
      <circle cx="18.5" cy="18" r="2" />
      <path d="M5.5 8v3a3 3 0 0 0 3 3h7a3 3 0 0 1 3 3v1" />
    </Icon>
  );
}

export function IconSettings(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="2.75" />
      <path d="M19.4 13.5a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V19.5a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1.08-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3.5a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1.08 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9.5a1.65 1.65 0 0 0 1-1.51V3.5a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.09a1.65 1.65 0 0 0 1.51 1H20.5a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </Icon>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="10.75" cy="10.75" r="6.25" />
      <path d="m19.5 19.5-4.35-4.35" />
    </Icon>
  );
}

export function IconPlus(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 4.5v15M4.5 12h15" />
    </Icon>
  );
}

export function IconEdit(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7.5 18.5 3 20l1.5-4.5 12-12Z" />
    </Icon>
  );
}

export function IconTrash(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 6.5h16M8.5 6.5V4.75A1.25 1.25 0 0 1 9.75 3.5h4.5a1.25 1.25 0 0 1 1.25 1.25V6.5M18 6.5 17.3 19a1.5 1.5 0 0 1-1.5 1.4H8.2A1.5 1.5 0 0 1 6.7 19L6 6.5" />
      <path d="M10 10.5v6M14 10.5v6" />
    </Icon>
  );
}

export function IconExternalLink(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M9 6H6.5A1.5 1.5 0 0 0 5 7.5v10A1.5 1.5 0 0 0 6.5 19h10a1.5 1.5 0 0 0 1.5-1.5V15" />
      <path d="M13.5 4.5H19v5.5M19 4.5 11 12.5" />
    </Icon>
  );
}

export function IconCalendar(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M3.5 9.5h17M8 3v4M16 3v4" />
    </Icon>
  );
}

export function IconTag(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M11.5 3.5H6A2.5 2.5 0 0 0 3.5 6v5.5a1.5 1.5 0 0 0 .44 1.06l8.5 8.5a1.5 1.5 0 0 0 2.12 0l6.94-6.94a1.5 1.5 0 0 0 0-2.12l-8.5-8.5a1.5 1.5 0 0 0-1.06-.44Z" />
      <path d="M8 8h0" />
    </Icon>
  );
}

export function IconArticle(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="4.5" y="3.5" width="15" height="17" rx="1.5" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </Icon>
  );
}

export function IconVideo(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="5.5" width="12" height="13" rx="1.75" />
      <path d="M15.5 10.2 20 7.5v9l-4.5-2.7" />
    </Icon>
  );
}

export function IconUrl(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M9.5 14.5 14.5 9.5" />
      <path d="M11 6.5 12.6 4.9a3.5 3.5 0 0 1 5 5L16 11.4M13 17.5l-1.6 1.6a3.5 3.5 0 0 1-5-5L8 12.5" />
    </Icon>
  );
}

export function IconNote(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 3.5h9l4.5 4.5V19a1.5 1.5 0 0 1-1.5 1.5H6A1.5 1.5 0 0 1 4.5 19V5A1.5 1.5 0 0 1 6 3.5Z" />
      <path d="M14.5 3.5V8H19M8 12h6M8 15.5h6" />
    </Icon>
  );
}

export function IconAlertTriangle(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M10.7 3.9 2.9 18.1a1.5 1.5 0 0 0 1.3 2.4h15.6a1.5 1.5 0 0 0 1.3-2.4L13.3 3.9a1.5 1.5 0 0 0-2.6 0Z" />
      <path d="M12 9.5v4.25M12 16.75h0" />
    </Icon>
  );
}

export function IconInbox(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 12.5h4.4l1.2 2.5h4.8l1.2-2.5H20" />
      <path d="M5.5 6 4 12.5V18a1.5 1.5 0 0 0 1.5 1.5h13A1.5 1.5 0 0 0 20 18v-5.5L18.5 6a1.5 1.5 0 0 0-1.45-1.5H6.95A1.5 1.5 0 0 0 5.5 6Z" />
    </Icon>
  );
}

export function IconSpinner(props: IconProps) {
  return (
    <Icon {...props} className={`animate-spin ${props.className ?? ""}`}>
      <path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5" strokeLinecap="round" />
    </Icon>
  );
}

export function IconChevronDown(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m6 9 6 6 6-6" />
    </Icon>
  );
}

export function IconChevronRight(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m9 6 6 6-6 6" />
    </Icon>
  );
}

export function IconSun(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" />
    </Icon>
  );
}

export function IconMoon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" />
    </Icon>
  );
}

export function IconCheckCircle(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m8.5 12.3 2.4 2.4 4.6-5.4" />
    </Icon>
  );
}

export function IconX(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m9.5 9.5 5 5m0-5-5 5" />
    </Icon>
  );
}

export function IconClock(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </Icon>
  );
}

export function IconSend(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M20.5 3.5 3 10.3l6.7 2.6M20.5 3.5 13.7 21l-4-8.1M20.5 3.5 9.7 13.2" />
    </Icon>
  );
}

export function IconSparkles(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M11 3.5 12.4 8l4.6 1.4-4.6 1.4L11 15.2 9.6 10.8 5 9.4l4.6-1.4L11 3.5Z" />
      <path d="M18 15.5 18.7 17.6 20.8 18.3 18.7 19 18 21.1 17.3 19 15.2 18.3 17.3 17.6 18 15.5Z" />
    </Icon>
  );
}

export function IconUser(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="8.25" r="3.25" />
      <path d="M5 19.5c0-3.6 3.1-6 7-6s7 2.4 7 6" />
    </Icon>
  );
}

export function IconEye(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.5 12S5.8 5.5 12 5.5 21.5 12 21.5 12 18.2 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.75" />
    </Icon>
  );
}

export function IconLogout(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M9 20H6.5A1.5 1.5 0 0 1 5 18.5v-13A1.5 1.5 0 0 1 6.5 4H9" />
      <path d="M15.5 16.5 20 12l-4.5-4.5M20 12H9.5" />
    </Icon>
  );
}

export function IconEyeOff(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 3l18 18" />
      <path d="M9.9 10.1a2.75 2.75 0 0 0 3.9 3.9" />
      <path d="M6.3 6.9C4 8.6 2.5 12 2.5 12S5.8 18.5 12 18.5a10 10 0 0 0 3.4-.6M10.6 5.6A9.6 9.6 0 0 1 12 5.5c6.2 0 9.5 6.5 9.5 6.5a13.7 13.7 0 0 1-3 4" />
    </Icon>
  );
}

export function IconPlay(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M7 5.5v13l11-6.5-11-6.5Z" fill="currentColor" stroke="none" />
    </Icon>
  );
}
