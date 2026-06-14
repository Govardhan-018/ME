import { forwardRef } from 'react'
import { motion, type HTMLMotionProps } from 'framer-motion'
import { cn } from '@/lib/utils'

interface GlassPanelProps extends HTMLMotionProps<'div'> {
  strong?: boolean
}

/** Frosted surface — the only "card" in the system. 24px geometry, 1px hairline. */
export const GlassPanel = forwardRef<HTMLDivElement, GlassPanelProps>(
  ({ className, strong, children, ...props }, ref) => (
    <motion.div
      ref={ref}
      className={cn(strong ? 'glass-strong' : 'glass', 'rounded-3xl', className)}
      {...props}
    >
      {children}
    </motion.div>
  )
)
GlassPanel.displayName = 'GlassPanel'
