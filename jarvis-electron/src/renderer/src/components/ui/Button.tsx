import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { motion } from 'framer-motion'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'
import { useMagnetic } from '@/hooks/useMagnetic'
import { springs } from '@/lib/motion'

const buttonVariants = cva(
  'no-drag relative inline-flex items-center justify-center gap-2 rounded-full font-medium tracking-wide whitespace-nowrap transition-colors duration-200 outline-none',
  {
    variants: {
      variant: {
        primary: 'bg-cyan/15 text-cyan border border-cyan/30 hover:bg-cyan/25 text-glow',
        solid: 'bg-cyan text-void border border-cyan hover:bg-cyan-soft',
        ghost: 'text-smoke hover:text-bone border border-transparent',
        glass: 'glass text-ash hover:text-bone'
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-10 px-4 text-sm',
        lg: 'h-12 px-6 text-sm',
        icon: 'h-10 w-10 p-0'
      }
    },
    defaultVariants: { variant: 'glass', size: 'md' }
  }
)

interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  magnetic?: boolean
  children?: ReactNode
}

export function Button({
  className,
  variant,
  size,
  magnetic = true,
  children,
  ...props
}: ButtonProps): JSX.Element {
  const mag = useMagnetic(0.3)
  const wrap = magnetic
    ? { ref: mag.ref, style: mag.style, onMouseMove: mag.onMouseMove, onMouseLeave: mag.onMouseLeave }
    : {}
  return (
    <motion.div
      className="no-drag inline-flex"
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.96 }}
      transition={springs.bouncy}
      {...wrap}
    >
      <button className={cn(buttonVariants({ variant, size }), className)} {...props}>
        {children}
      </button>
    </motion.div>
  )
}
