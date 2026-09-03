"use client";

import { useState, type FormEvent } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api/client";
import { IconAlertTriangle, IconUser } from "@/components/ui/icons";
import type { UserPublic, UserUpdateInput } from "@/lib/types/auth";

interface EditProfileDialogProps {
  user: UserPublic;
  onClose: () => void;
  onSubmit: (payload: UserUpdateInput) => Promise<void>;
}

/** Edit-profile form. Email is shown but not editable -- it's the sign-in
 * identifier and the backend has no endpoint for changing it. */
export function EditProfileDialog({ user, onClose, onSubmit }: EditProfileDialogProps) {
  const [name, setName] = useState(user.name ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    setFieldErrors({});

    try {
      await onSubmit({ name: name.trim() ? name.trim() : null });
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors ?? {});
        setFormError(err.fieldErrors ? null : err.message);
      } else {
        setFormError("Something went wrong. Try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title="Edit profile" onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
        <Input
          label="Display name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Ada Lovelace"
          icon={<IconUser className="h-4 w-4" />}
          error={fieldErrors.name}
          maxLength={100}
          autoFocus
          helperText={
            !fieldErrors.name ? "Shown across StudyGraph. Leave blank to remove it." : undefined
          }
        />

        <Input
          label="Email"
          value={user.email}
          disabled
          helperText="Your email is your sign-in identifier and can't be changed here."
        />

        {formError && (
          <p className="flex items-start gap-2 rounded-lg border border-danger/20 bg-danger/5 px-3 py-2 text-xs text-danger">
            <IconAlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {formError}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" loading={submitting}>
            Save changes
          </Button>
        </div>
      </form>
    </Modal>
  );
}
