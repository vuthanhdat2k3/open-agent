import { z } from "zod";

export const capabilitiesSchema = z.object({
  blocked_reasons: z.record(z.string()).optional(),
}).catchall(z.union([z.boolean(), z.record(z.string())]));

export const metaSchema = z.object({
  server_time: z.string().datetime(),
  correlation_id: z.string().optional(),
  reason_registry_version: z.string().optional(),
});

export const listEnvelopeSchema = z.object({
  items: z.array(z.unknown()),
  page: z.object({ next_cursor: z.string().nullable(), has_more: z.boolean() }),
  filtered_counts: z.object({ total: z.number(), urgent: z.number() }).optional(),
  meta: metaSchema,
});

export type CapabilitiesPayload = z.infer<typeof capabilitiesSchema>;
export type ListEnvelope<T> = Omit<z.infer<typeof listEnvelopeSchema>, "items"> & { items: T[] };
