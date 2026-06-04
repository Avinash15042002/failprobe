import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

/** Placeholder shown on pages whose functionality lands in Phase 2 (Month 2). */
export function ComingSoon({ title }: { title: string }) {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <Card>
        <CardHeader>
          <CardTitle>Coming in Phase 2</CardTitle>
          <CardDescription>
            This page is part of the Month 2 deliverable and is not yet
            implemented.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Check back once the evaluation, comparison, and review APIs ship.
        </CardContent>
      </Card>
    </div>
  );
}
