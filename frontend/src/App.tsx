import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import MiniApp from "@/miniapp/MiniApp";
import AdminApp from "@/admin/AdminApp";
import Landing from "@/Landing";

export default function App() {
  return (
    <div className="dark min-h-screen bg-background text-foreground grain">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/app/*" element={<MiniApp />} />
          <Route path="/admin/*" element={<AdminApp />} />
        </Routes>
      </BrowserRouter>
      <Toaster theme="dark" position="top-center" richColors />
    </div>
  );
}
