import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import ProductValidation from "./pages/ProductValidation";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider>
      <AuthProvider>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          {/* Décor IT Spirit — blobs fixés en arrière-plan global */}
          <div className="its-blob its-blob-1" aria-hidden="true" />
          <div className="its-blob its-blob-2" aria-hidden="true" />
          <div className="its-blob its-blob-3" aria-hidden="true" />
          <div className="relative z-[1]">
            <BrowserRouter basename="/mail-to-biz">
              <Routes>
                <Route path="/" element={<Index />} />
                <Route path="/products/validation" element={<ProductValidation />} />
                {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
                <Route path="*" element={<NotFound />} />
              </Routes>
            </BrowserRouter>
          </div>
        </TooltipProvider>
      </AuthProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
