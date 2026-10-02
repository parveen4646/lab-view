import { useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiService, QASource } from '@/services/api';
import { MessageCircle, X, Send, Loader2 } from 'lucide-react';

interface ChatWidgetProps {
  reportId?: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  sources?: QASource[];
}

export function ChatWidget({ reportId }: ChatWidgetProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSend = async () => {
    const question = input.trim();
    if (!question || isLoading) return;

    setInput('');
    setMessages((prev) => [...prev, { role: 'user', text: question }]);
    setIsLoading(true);

    try {
      const response = await apiService.askQuestion(question, reportId);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: response.answer, sources: response.sources },
      ]);
    } catch (error) {
      console.warn('Q&A request failed:', error);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: "Sorry, I couldn't get an answer right now. Please try again." },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-foreground text-background shadow-lg transition-transform hover:scale-105"
        aria-label="Ask about your labs"
      >
        <MessageCircle className="h-6 w-6" />
      </button>
    );
  }

  return (
    <Card className="fixed bottom-5 right-5 z-50 flex h-[480px] w-[340px] flex-col overflow-hidden p-0 shadow-xl">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b p-3">
        <p className="text-sm font-semibold text-foreground">Ask about your labs</p>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => setIsOpen(false)}
          aria-label="Close chat"
        >
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>

      <CardContent className="flex-1 space-y-3 overflow-y-auto p-3">
        {messages.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Ask a general question about lab markers — e.g. "What does high LDL mean?"
            {reportId ? ' You can also ask about your most recent report.' : ''}
          </p>
        )}

        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                message.role === 'user'
                  ? 'bg-foreground text-background'
                  : 'bg-muted text-foreground'
              }`}
            >
              <p className="whitespace-pre-wrap">{message.text}</p>
              {message.sources && message.sources.length > 0 && (
                <p className="mt-1.5 text-xs text-muted-foreground">
                  Sources: {message.sources.map((s) => s.source).join(', ')}
                </p>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-1.5 rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Thinking…
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </CardContent>

      <div className="flex items-center gap-2 border-t p-3">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question…"
          disabled={isLoading}
          className="h-9 text-sm"
        />
        <Button
          size="icon"
          className="h-9 w-9 shrink-0"
          onClick={handleSend}
          disabled={isLoading || !input.trim()}
          aria-label="Send question"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </Card>
  );
}
