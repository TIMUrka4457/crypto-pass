import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import MiniApp from "@/miniapp/MiniApp";
import Business from "@/Landing";
import Home from "@/site/Home";
import { HowItWorks, Fees, Faq } from "@/site/Pages";
import AdminGate, { NotFound } from "@/AdminGate";

export default function App() {
  return (
    <div className="dark min-h-screen bg-background text-foreground grain">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/how-it-works" element={<HowItWorks />} />
          <Route path="/fees" element={<Fees />} />
          <Route path="/business" element={<Business />} />
          <Route path="/faq" element={<Faq />} />
          <Route path="/app/*" element={<MiniApp />} />
          <Route path="/admin/*" element={<NotFound />} />
          <Route path="/:key/*" element={<AdminGate />} />
        </Routes>
      </BrowserRouter>
      <Toaster theme="dark" position="top-center" richColors />
    </div>
  );
}
