import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SidePanel } from '../src/components/ui/SidePanel'

describe('SidePanel', () => {
  it('announces itself as a dialog', () => {
    render(
      <SidePanel title="Shenzhen Precision Parts" onClose={() => {}}>
        <p>body</p>
      </SidePanel>,
    )

    const dialog = screen.getByRole('dialog', { name: 'Shenzhen Precision Parts' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('closes on escape, not only on a click', () => {
    // The backdrop and the close button are both mouse-only ways out.
    const onClose = vi.fn()
    render(
      <SidePanel title="Panel" onClose={onClose}>
        <p>body</p>
      </SidePanel>,
    )

    return userEvent.keyboard('{Escape}').then(() => {
      expect(onClose).toHaveBeenCalledOnce()
    })
  })

  it('closes from the button', async () => {
    const onClose = vi.fn()
    render(
      <SidePanel title="Panel" onClose={onClose}>
        <p>body</p>
      </SidePanel>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('moves focus into the panel so the keyboard starts inside it', () => {
    render(
      <SidePanel title="Panel" onClose={() => {}}>
        <p>body</p>
      </SidePanel>,
    )

    expect(screen.getByRole('dialog')).toHaveFocus()
  })

  it('does not close when the panel itself is clicked', async () => {
    const onClose = vi.fn()
    render(
      <SidePanel title="Panel" onClose={onClose}>
        <p>body text</p>
      </SidePanel>,
    )

    await userEvent.click(screen.getByText('body text'))

    expect(onClose).not.toHaveBeenCalled()
  })
})
