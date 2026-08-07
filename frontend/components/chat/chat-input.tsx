"use client";

import { Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { ChatConnectionBanner, type ConnectionState } from "@/components/chat/chat-connection-banner";

interface ChatInputProps {
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  streaming: boolean;
  disabled: boolean;
  connectionState: ConnectionState;
}

// Composer + connection banner. `onSubmit` is the page's `send`, called from
// both the form submit and Enter-to-send; Shift+Enter still inserts a
// newline via the browser default (no special-cased here, unchanged).
export function ChatInput({ draft, onDraftChange, onSubmit, streaming, disabled, connectionState }: ChatInputProps) {
  return (
    <div className="sticky bottom-0 mt-3 border-t border-border bg-background/95 pt-3 backdrop-blur-sm">
      <ChatConnectionBanner state={connectionState} />
      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!streaming) onSubmit();
        }}
      >
        <label htmlFor="chat-composer" className="sr-only">Message</label>
        <Textarea
          id="chat-composer"
          name="message"
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          className="min-h-[48px] flex-1 resize-none text-xs"
        />
        <Button
          type={streaming ? "button" : "submit"}
          onClick={streaming ? onSubmit : undefined}
          disabled={disabled}
          className="h-10 gap-2 self-end px-5 text-xs"
          variant={streaming ? "outline" : "default"}
          title={streaming ? "Stop streaming" : "Send message"}
        >
          {streaming ? (
            <>
              <Square className="h-3.5 w-3.5" aria-hidden="true" />
              Stop
            </>
          ) : (
            <>
              <Send className="h-3.5 w-3.5" aria-hidden="true" />
              Send
            </>
          )}
        </Button>
      </form>
    </div>
  );
}
