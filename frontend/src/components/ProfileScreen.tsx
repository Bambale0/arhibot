import { useEffect, useState } from 'react'
import * as api from '../api'
import { useAuth } from '../auth'
import type { BillingSummary } from '../types'
import { LogOutIcon, UserIcon } from './Icons'

function rub(value: string) {
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(Number(value))
}

function paymentLabel(status: string) {
  if (status === 'succeeded') return 'Оплачен'
  if (status === 'canceled') return 'Отменён'
  if (status === 'failed') return 'Ошибка'
  return 'Ожидает оплаты'
}

export function ProfileScreen({ onOpenAdmin }: { onOpenAdmin?: () => void }) {
  const { user, signOut } = useAuth()
  const [billing, setBilling] = useState<BillingSummary | null>(null)
  const [billingError, setBillingError] = useState<string | null>(null)
  const [busyPackage, setBusyPackage] = useState<string | null>(null)
  const [paymentNotice, setPaymentNotice] = useState<string | null>(null)
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'

  async function loadBilling() {
    try {
      setBilling(await api.getBillingSummary())
      setBillingError(null)
    } catch (error) {
      setBillingError(error instanceof Error ? error.message : 'Не удалось загрузить оплату')
    }
  }

  useEffect(() => {
    let cancelled = false
    async function bootstrapBilling() {
      const params = new URLSearchParams(window.location.search)
      const paymentId = params.get('payment_id')
      try {
        if (paymentId) {
          const payment = await api.getBillingPayment(paymentId)
          if (!cancelled) {
            setPaymentNotice(
              payment.status === 'succeeded'
                ? `Оплата прошла. Начислено ${payment.credits} кредитов.`
                : payment.status === 'canceled'
                  ? 'Платёж отменён.'
                  : 'Платёж обрабатывается. Баланс обновится после подтверждения YooKassa.',
            )
          }
          params.delete('billing')
          params.delete('payment_id')
          const query = params.toString()
          window.history.replaceState({}, '', `${window.location.pathname}${query ? `?${query}` : ''}`)
        }
        const summary = await api.getBillingSummary()
        if (!cancelled) setBilling(summary)
      } catch (error) {
        if (!cancelled) setBillingError(error instanceof Error ? error.message : 'Не удалось проверить платёж')
      }
    }
    void bootstrapBilling()
    return () => { cancelled = true }
  }, [])

  async function buy(packageCode: string) {
    setBusyPackage(packageCode)
    setBillingError(null)
    try {
      const payment = await api.createBillingPayment(packageCode)
      if (!payment.confirmation_url) throw new Error('YooKassa не вернула ссылку на оплату')
      window.location.assign(payment.confirmation_url)
    } catch (error) {
      setBillingError(error instanceof Error ? error.message : 'Не удалось создать платёж')
      setBusyPackage(null)
    }
  }

  return (
    <section className="page-content profile-page">
      <div className="page-heading-row"><div><span className="eyebrow">АККАУНТ AUROOM</span><h1>Профиль</h1><p>Аккаунт, баланс и оплата генераций.</p></div>{isAdmin && onOpenAdmin && <button className="primary-button" onClick={onOpenAdmin}>Веб-админка</button>}</div>

      {paymentNotice && <div className="billing-notice">{paymentNotice}</div>}
      {billingError && <div className="banner-error">{billingError}<button onClick={() => setBillingError(null)}>Закрыть</button></div>}

      <div className="profile-card">
        <div className="profile-avatar"><UserIcon /></div>
        <div className="profile-main"><h2>{user?.display_name || 'Пользователь AuRoom'}</h2><span className="status-pill">{user?.role || 'user'}</span></div>
        <dl className="profile-details">
          <div><dt>Баланс</dt><dd><strong>{billing?.credits_balance ?? user?.credits_balance ?? 0} кредитов</strong></dd></div>
          <div><dt>ID</dt><dd>{user?.id}</dd></div>
          <div><dt>Создан</dt><dd>{user?.created_at ? new Intl.DateTimeFormat('ru-RU', { dateStyle: 'long' }).format(new Date(user.created_at)) : '—'}</dd></div>
          <div><dt>Режим</dt><dd>Telegram Mini App / Web</dd></div>
        </dl>
        <button className="secondary-button profile-logout" onClick={() => void signOut()}><LogOutIcon /> Выйти</button>
      </div>

      <section className="billing-section">
        <div className="section-title-row"><div><span className="eyebrow">ОПЛАТА ЧЕРЕЗ ЮKASSA</span><h2>Пополнить баланс</h2></div><span>Безопасная оплата на стороне YooKassa</span></div>
        {!billing ? (
          <div className="empty-inline">Загружаем тарифы…</div>
        ) : !billing.enabled ? (
          <div className="empty-inline">Оплата ещё не активирована. Администратор публикует тарифы в веб-админке; YooKassa credentials хранятся только на сервере.</div>
        ) : (
          <div className="billing-packages">
            {billing.packages.map((item) => (
              <article className="billing-package" key={item.code}>
                <span className="eyebrow">{item.credits} КРЕДИТОВ</span>
                <h3>{item.label}</h3>
                <strong className="billing-price">{rub(item.amount)}</strong>
                <button className="primary-button" disabled={busyPackage !== null} onClick={() => void buy(item.code)}>
                  {busyPackage === item.code ? 'Создаём платёж…' : 'Оплатить'}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      {billing && billing.payments.length > 0 && (
        <section className="billing-section">
          <div className="section-title-row"><div><span className="eyebrow">ПОСЛЕДНИЕ ОПЕРАЦИИ</span><h2>Платежи</h2></div><button className="secondary-button" onClick={() => void loadBilling()}>Обновить</button></div>
          <div className="billing-history">
            {billing.payments.slice(0, 8).map((payment) => (
              <div className="billing-history-row" key={payment.id}>
                <div><strong>{payment.credits} кредитов</strong><span>{new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(payment.created_at))}</span></div>
                <div><strong>{rub(payment.amount)}</strong><span className={`payment-status status-${payment.status}`}>{paymentLabel(payment.status)}</span></div>
              </div>
            ))}
          </div>
        </section>
      )}
    </section>
  )
}
