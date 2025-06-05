#include "stm32f1xx_hal.h"

#define RX_BUF_SIZE 260
volatile uint8_t rx_buffer[RX_BUF_SIZE];
volatile uint16_t rx_index = 0;

void uart_init(void) {
    // Bật clock cho GPIOA và USART1
    RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_USART1EN;

    // PA9 (TX) là output push-pull, 50MHz
    GPIOA->CRH &= ~(GPIO_CRH_CNF9 | GPIO_CRH_MODE9);
    GPIOA->CRH |= (0x0B << 4); // MODE9 = 11 (50MHz), CNF9 = 10 (AF Push-pull)

    // PA10 (RX) là input floating
    GPIOA->CRH &= ~(GPIO_CRH_CNF10 | GPIO_CRH_MODE10);
    GPIOA->CRH |= (0x04 << 8); // MODE10 = 00, CNF10 = 01 (floating input)

    // Cấu hình USART1: 115200, 8N1
    USART1->BRR = SystemCoreClock / 115200; // Giả sử HCLK = 72MHz
    USART1->CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_RXNEIE | USART_CR1_UE;

    // Bật ngắt USART1 trong NVIC
    NVIC_EnableIRQ(USART1_IRQn);
}

void USART1_IRQHandler(void) {
    if (USART1->SR & USART_SR_RXNE) {
        uint8_t b = USART1->DR; // Đọc dữ liệu nhận
        if (rx_index < RX_BUF_SIZE) {
            rx_buffer[rx_index++] = b;
        }
        // Kiểm tra nếu đã nhận đủ 1 frame
        if (rx_index >= 4) { // tối thiểu: model(1) + id(2) + len(1)
            uint8_t model = rx_buffer[0];
            uint8_t id_len = (model == 0) ? 2 : 4;
            if (rx_index >= 1 + id_len + 1) {
                uint8_t data_len = rx_buffer[1 + id_len];
                if (rx_index >= 1 + id_len + 1 + data_len) {
                    // Đã nhận đủ frame
                    process_uart_frame((uint8_t*)rx_buffer, 1 + id_len + 1 + data_len);
                    rx_index = 0; // reset buffer
                }
            }
        }
    }
}

void process_uart_frame(uint8_t *frame, uint16_t len) {
    // Giải mã frame
    uint8_t model = frame[0];
    uint32_t id = 0;
    if (model == 0)
        id = (frame[1] << 8) | frame[2];
    else
        id = (frame[1] << 24) | (frame[2] << 16) | (frame[3] << 8) | frame[4];
    uint8_t id_len = (model == 0) ? 2 : 4;
    uint8_t data_len = frame[1 + id_len];
    uint8_t *data = &frame[1 + id_len + 1];

    // Xử lý dữ liệu ở đây (ví dụ: bật LED, gửi CAN, ...)
}

int main(void) {
    uart_init();
    while (1) {
        // Main loop, có thể xử lý thêm ở đây
    }
}