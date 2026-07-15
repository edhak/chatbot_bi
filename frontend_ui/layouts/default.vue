<template>
  <div class="flex h-screen flex-col overflow-hidden bg-[#F4F6F8] text-brand-dark">
    <AppNavbar />
    <div class="flex min-h-0 flex-1 overflow-hidden">
      <main class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <slot />
      </main>
    </div>
  </div>
</template>
