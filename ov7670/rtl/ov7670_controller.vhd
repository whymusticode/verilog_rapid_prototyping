library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity ov7670_controller is
    Port ( clk             : in    STD_LOGIC;
           resend          : in    STD_LOGIC;
           config_finished : out   STD_LOGIC;
           sioc            : out   STD_LOGIC;
           siod            : inout STD_LOGIC;
           reset           : out   STD_LOGIC;
           pwdn            : out   STD_LOGIC;
           xclk            : out   STD_LOGIC);
end ov7670_controller;

architecture Behavioral of ov7670_controller is
    COMPONENT OV7670_registers
    PORT(
        clk      : IN  std_logic;
        advance  : IN  std_logic;
        command  : OUT std_logic_vector(15 downto 0);
        finished : OUT std_logic
    );
    END COMPONENT;

    COMPONENT i2c_sender
    PORT(
        clk   : IN    std_logic;
        send  : IN    std_logic;
        taken : OUT   std_logic;
        id    : IN    std_logic_vector(7 downto 0);
        reg   : IN    std_logic_vector(7 downto 0);
        value : IN    std_logic_vector(7 downto 0);
        siod  : inout std_logic;
        sioc  : out   std_logic
    );
    END COMPONENT;

    signal sys_clk  : std_logic := '0';
    signal command   : std_logic_vector(15 downto 0);
    signal finished  : std_logic := '0';
    signal taken     : std_logic := '0';
    signal send      : std_logic := '0';

    signal camera_address : std_logic_vector(7 downto 0) := x"42";

begin
    config_finished <= finished;
    reset <= '1';
    pwdn  <= '0';
    xclk  <= sys_clk;

    Inst_i2c_sender: i2c_sender PORT MAP(
        clk   => clk,
        taken => taken,
        siod  => siod,
        sioc  => sioc,
        send  => send,
        id    => camera_address,
        reg   => command(15 downto 8),
        value => command(7 downto 0)
    );

    Inst_OV7670_registers: OV7670_registers PORT MAP(
        clk      => clk,
        advance  => taken,
        command  => command,
        finished => finished
    );

    process(clk)
    begin
        if rising_edge(clk) then
            if resend = '1' then
                sys_clk <= '0';
                send    <= '0';
            elsif finished = '0' then
                send <= '1';
            else
                send <= '0';
            end if;
            sys_clk <= not sys_clk;
        end if;
    end process;

end Behavioral;
