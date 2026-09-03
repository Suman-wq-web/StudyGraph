"use client";

import { useState, type FormEvent } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { IconAlertTriangle, IconUrl } from "@/components/ui/icons";
import { ApiError } from "@/lib/api/client";
import {
  RESOURCE_TYPE_LABELS,
  RESOURCE_TYPES,
  type Resource,
  type ResourceCreateInput,
  type ResourceType,
  type ResourceUpdateInput,
} from "@/lib/types/resource";

interface ResourceFormDialogProps {
  resource?: Resource;
  onClose: () => void;
  onSubmit: (payload: ResourceCreateInput | ResourceUpdateInput) => Promise<void>;
}

/** Shared add/edit form for a resource. Backend validation errors highlight the matching field. */
export function ResourceFormDialog({ resource, onClose, onSubmit }: ResourceFormDialogProps) {
  const isEdit = Boolean(resource);

  const [title, setTitle] = useState(resource?.title ?? "");
  const [type, setType] = useState<ResourceType>(resource?.type ?? "article");
  const [description, setDescription] = useState(resource?.description ?? "");
  const [sourceUrl, setSourceUrl] = useState(resource?.sourceUrl ?? "");
  const [content, setContent] = useState(resource?.content ?? "");
  const [tagsInput, setTagsInput] = useState(resource?.tags.join(", ") ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const showSourceUrl = type !== "note";
  const showContent = type === "note" || type === "article";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    setFieldErrors({});

    const tags = tagsInput
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);

    const payload: ResourceCreateInput | ResourceUpdateInput = {
      title,
      type,
      description: description.trim() ? description.trim() : null,
      sourceUrl: sourceUrl.trim() ? sourceUrl.trim() : null,
      content: content.trim() ? content.trim() : null,
      tags,
    };

    try {
      await onSubmit(payload);
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
    <Modal title={isEdit ? "Edit resource" : "Add resource"} onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
        <Input
          label="Title"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Attention Is All You Need"
          error={fieldErrors.title}
          maxLength={200}
        />

        <Select
          label="Type"
          value={type}
          onChange={(e) => setType(e.target.value as ResourceType)}
          error={fieldErrors.type}
        >
          {RESOURCE_TYPES.map((t) => (
            <option key={t} value={t}>
              {RESOURCE_TYPE_LABELS[t]}
            </option>
          ))}
        </Select>

        {showSourceUrl && (
          <Input
            label="Source URL"
            type="url"
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            placeholder="https://..."
            icon={<IconUrl className="h-4 w-4" />}
            error={fieldErrors.sourceUrl}
            helperText={!fieldErrors.sourceUrl ? "Where this resource originally came from." : undefined}
          />
        )}

        <Textarea
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="Optional short summary"
          error={fieldErrors.description}
          maxLength={2000}
        />

        {showContent && (
          <Textarea
            label={type === "note" ? "Note content" : "Content (optional)"}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={4}
            placeholder={type === "note" ? "Write your note..." : "Paste article text..."}
            error={fieldErrors.content}
          />
        )}

        <Input
          label="Tags"
          value={tagsInput}
          onChange={(e) => setTagsInput(e.target.value)}
          placeholder="comma, separated, tags"
          error={fieldErrors.tags}
          helperText={!fieldErrors.tags ? "Up to 20 tags, separated by commas." : undefined}
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
            {isEdit ? "Save changes" : "Add resource"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
