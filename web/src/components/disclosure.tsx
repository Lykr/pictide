import { useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from './ui/collapsible';
import { Button } from './ui/button';

export function Disclosure({ title, children, ...props }: { title: ReactNode; children: ReactNode; id?: string; className?: string; hidden?: boolean }) {
  const [open, setOpen] = useState(false);
  return <Collapsible {...props} open={open} onOpenChange={setOpen}>
    <CollapsibleTrigger asChild><Button variant="ghost" className="collapsible-label">{open ? <ChevronDown /> : <ChevronRight />}{title}</Button></CollapsibleTrigger>
    <CollapsibleContent forceMount hidden={!open}>{children}</CollapsibleContent>
  </Collapsible>;
}
