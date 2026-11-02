// Home page: shows the hello card that proves browser -> backend -> database works.
import { HelloCard } from "@/components/HelloCard";

export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <HelloCard />
    </main>
  );
}
